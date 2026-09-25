"""Discrete-event service simulation. Synthetic execution times, real elapsed decision time on replay."""
import heapq, itertools, random, math
from collections import Counter, deque
from src.schema import FIELDS
from src.intent_cache import IntentCache

def workload(fixture,kind='steady',n=1000,seed=42,semantic='changing'):
    rng=random.Random(seed); arrivals=[]; t=0.; segment=0
    while len(arrivals)<n:
        rate=2. if kind=='steady' else (0.5 if segment%2==0 else 8.)
        end=(segment+1)*20
        while True:
            t+=rng.expovariate(rate)
            if t>=end: t=end;break
            pool=fixture if semantic=='changing' else fixture[:5]
            item=rng.choice(pool)
            arrivals.append(dict(id=len(arrivals),arrival=t,intent_id=item['id'],text=item['text'],
              truth=item['truth'],origin=rng.randrange(4),size_mb=rng.uniform(.25,2.)))
            if len(arrivals)==n:break
        segment+=1
    return arrivals

def simulate(arrivals,decide,deadline,queue_limit=32,timeout=3.,concurrency=1,cache=False,controller_trace=None):
    """Replay model timings, or an externally recorded real-time admission timeline.

    controller_trace bypasses synthetic admission scheduling. Network and execution
    events still share one timeline, so each decision sees the latest node state.
    It does not turn simulated execution into a physically deployed edge service.
    """
    if type(concurrency) is not int or concurrency<1:raise ValueError('invalid concurrency')
    if deadline<=0 or queue_limit<0:raise ValueError('invalid deadline/queue limit')
    if len({a['id'] for a in arrivals})!=len(arrivals):raise ValueError('duplicate arrival ids')
    if controller_trace is not None and set(controller_trace)!={a['id'] for a in arrivals}:
        raise ValueError('incomplete external controller trace')
    events=[];counter=itertools.count();rows={};waiting=deque();active=set()
    semantic_cache=IntentCache() if cache else None
    nodes=[dict(running=None,finish=0.,pending=[]) for _ in range(5)]
    def event(t,kind,rid): heapq.heappush(events,(t,next(counter),kind,rid))
    for a in arrivals:
        rows[a['id']]=dict(a,deadline=a['arrival']+deadline,status='pending')
        event(a['arrival'],'arrival',a['id'])
    def prune(now):
        keep=deque()
        while waiting:
            i=waiting.popleft()
            if rows[i]['deadline']<=now:
                rows[i].update(status='queue_expired',terminal=rows[i]['deadline'])
            else:keep.append(i)
        waiting.extend(keep)
    def valid_labels(pred):
        return isinstance(pred,dict) and set(pred)==set(FIELDS) and all(pred[f] in v for f,v in FIELDS.items())
    def cached_start(r,now):
        labels=semantic_cache.lookup(r['text'],now) if semantic_cache else None
        if labels is None:return False
        r.update(decision_start=now,queue_wait_s=now-r['arrival'],decision_elapsed_s=0.,
          predicted=labels,decision_metadata={'cache_hit':True,'api_calls':0,'cost_usd':0.},decision_timed_out=False)
        event(now,'decision_done',r['id']);return True
    def start_controller(now):
        if controller_trace is not None:return
        prune(now)
        while waiting and len(active)<concurrency:
            rid=waiting.popleft();r=rows[rid]
            if cached_start(r,now):continue
            active.add(rid)
            # Offline callbacks only: elapsed time advances the virtual clock.
            r['decision_start']=now
            labels,elapsed,extra=decide(r)
            if not math.isfinite(elapsed) or elapsed<0:raise ValueError('invalid decision time')
            r.update(queue_wait_s=now-r['arrival'],decision_elapsed_s=elapsed,
              predicted=labels,decision_metadata=extra,decision_timed_out=elapsed>timeout)
            event(now+min(elapsed,timeout),'decision_done',rid)
    def start_service(node,now):
        state=nodes[node]
        if state['running'] is not None:return
        ready=[i for i in state['pending'] if rows[i]['network_ready']<=now]
        if not ready:return
        i=min(ready,key=lambda i:(rows[i]['priority'],rows[i]['network_ready'],i))
        state['pending'].remove(i);state['running']=i
        r=rows[i];r['service_start']=now;state['finish']=now+r['service_s']
        event(state['finish'],'service_done',i)
    while events:
        now,_,kind,i=heapq.heappop(events);r=rows[i]
        if kind=='arrival':
            if controller_trace is not None:
                trace=controller_trace[i]
                if 'decision_start' not in trace:
                    r.update(status=trace['status'],terminal=trace['terminal'])
                    continue
                for key in ['decision_start','decision_elapsed_s','predicted','decision_metadata','decision_timed_out']:
                    r[key]=trace[key]
                if r['decision_start']<r['arrival'] or trace['decision_end']<r['decision_start']:
                    raise ValueError('invalid external decision timeline')
                r['queue_wait_s']=r['decision_start']-r['arrival']
                event(trace['decision_end'],'decision_done',i)
                continue
            prune(now)
            if cached_start(r,now):continue
            if len(active)>=concurrency and len(waiting)>=queue_limit:
                r.update(status='queue_overflow',terminal=now)
            else:waiting.append(i);start_controller(now)
        elif kind=='decision_done':
            active.discard(i);r['decision_end']=now
            pred=r['predicted']
            valid=valid_labels(pred)
            if semantic_cache and valid and not r['decision_timed_out']:
                semantic_cache.store(r['text'],pred,now)
            if r['decision_timed_out']:r.update(status='decision_timeout',terminal=now)
            elif not valid:r.update(status='invalid_decision',terminal=now)
            elif now>=r['deadline']:r.update(status='decision_late',terminal=now)
            elif pred['service_type']=='unsupported':r.update(status='unsupported',terminal=now)
            else:
                candidates=range(5) if pred['locality']=='remote_allowed' else [r['origin']]
                priority=0 if pred['urgency']=='urgent' else 1
                options=[]
                for node in candidates:
                    transfer=(.002 if node==r['origin'] else .02 if node<4 else .06)+8*r['size_mb']/(1000 if node==r['origin'] else 100 if node<4 else 50)
                    duration={'count':.04,'detection':.08,'ocr':.06}[pred['service_type']]
                    duration*=1.8 if pred['quality_floor']=='high' else 1.
                    duration*=1+node*.1 if node<4 else .65
                    state=nodes[node]
                    work=sum(rows[j]['service_s'] for j in state['pending'] if rows[j]['priority']<=priority)
                    estimate=max(now+transfer,state['finish'])+work+duration
                    if estimate<=r['deadline']:options.append((estimate,node,transfer,duration))
                if not options:r.update(status='no_feasible_node',terminal=now)
                else:
                    _,node,transfer,duration=min(options)
                    r.update(node=node,network_ready=now+transfer,transfer_s=transfer,service_s=duration,priority=priority)
                    nodes[node]['pending'].append(i);event(now+transfer,'network_ready',i)
            start_controller(now)
        elif kind=='network_ready':start_service(r['node'],now)
        elif kind=='service_done':
            node=r['node'];nodes[node]['running']=None
            joint=r['predicted']==r['truth']
            locality_ok=r['truth']['locality']=='remote_allowed' or node==r['origin']
            quality_ok=r['truth']['quality_floor']!='high' or r['predicted']['quality_floor']=='high'
            good=joint and locality_ok and quality_ok and now<=r['deadline']
            r.update(status='success' if good else 'wrong_or_late',terminal=now,
              joint_correct=joint,locality_ok=locality_ok,quality_ok=quality_ok)
            start_service(node,now)
    result=list(rows.values())
    assert all(r['status']!='pending' for r in result)
    return result

def summarize(rows):
    counts=Counter(r['status'] for r in rows)
    waits=[r['queue_wait_s'] for r in rows if 'queue_wait_s' in r]
    costs=[r.get('decision_metadata',{}).get('cost_usd',0.) for r in rows]
    known=sum(c for c in costs if c is not None)
    supported=sum(r['truth']['service_type']!='unsupported' for r in rows)
    return dict(n=len(rows),success_rate=counts['success']/len(rows) if rows else 0,counts=dict(counts),
      mean_decision_queue_s=sum(waits)/len(waits) if waits else 0,
      useful_throughput_s=counts['success']/max(1e-12,max(r['terminal'] for r in rows)-min(r['arrival'] for r in rows)) if rows else 0,
      known_decision_cost_usd=known,unknown_cost_requests=sum(c is None for c in costs),
      decision_cost_per_success_usd=known/counts['success'] if counts['success'] and None not in costs else None,
      api_calls=sum(r.get('decision_metadata',{}).get('api_calls',0) for r in rows),
      cache_hits=sum(bool(r.get('decision_metadata',{}).get('cache_hit')) for r in rows),
      supported_arrivals=supported,
      success_rate_among_supported=counts['success']/supported if supported else None,
      correct_unsupported_rejections=sum(r['status']=='unsupported' and r['truth']['service_type']=='unsupported' for r in rows))
