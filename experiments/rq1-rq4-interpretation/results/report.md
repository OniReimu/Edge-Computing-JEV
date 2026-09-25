# EXP-2026-001 Analysis Report & Addendum A1 Synthesis

**Generated:** 2026-09-24 21:35 UTC | **Protocol:** Frozen analysis-plan.md + Addendum A1

## 1. Executive Summary

- **Coverage**: see Section 2 (strict mode exits non-zero if any expected cell is missing or has n != 300).
- **Oracle Positive Control**: FLAGGED (some cells deviated from EM 1.0).
- **Confirmatory results**: see `hypotheses.md` (every verdict there is computed from `hypotheses.csv`).

## 2. Coverage Matrix

| Condition | Jev-1.13.0 | DeepSeek-V4.1-Flash | GLM-5.3-Flash | Qwen3.8-Flash | SemIf-Qwen3.5-4B | Laya | Qwen3.5-4B-JSON |
|---|---|---|---|---|---|---|---|
| RQ1a/base | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ1a/pad_512 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ1a/pad_2048 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ1a/pad_8192 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ1a/pad_16384 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ1b/k1 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ1b/k2 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ1b/k4 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ1b/k8 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ2/clean | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ2/codeswitch | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ2/colloquial | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ2/defaultbait | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ2/keyvalue | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ2/negation | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ2/noise | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ2/revised | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ3/F4_low | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ3/F4_medium | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ3/F4_high | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ3/F6_low | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ3/F6_medium | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ3/F6_high | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ3/F8_low | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ3/F8_medium | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ3/F8_high | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ4/K4 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ4/K15 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ4/K64 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ4/K128 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ4/K254 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ4/churn25 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |
| RQ4/churn50 | 300 | 300 | 300 | 300 | 300 | 300 | 300 |

### Reference Interpreters Coverage

| Reference Model | Condition | Rows | Status |
|---|---|---|---|
| Rule | RQ1a/base | 300 | PASS |
| Rule | RQ1a/pad_512 | 300 | PASS |
| Rule | RQ1a/pad_2048 | 300 | PASS |
| Rule | RQ1a/pad_8192 | 300 | PASS |
| Rule | RQ1a/pad_16384 | 300 | PASS |
| Rule | RQ1b/k1 | 300 | PASS |
| Rule | RQ1b/k2 | 300 | PASS |
| Rule | RQ1b/k4 | 300 | PASS |
| Rule | RQ1b/k8 | 300 | PASS |
| Rule | RQ2/clean | 300 | PASS |
| Rule | RQ2/codeswitch | 300 | PASS |
| Rule | RQ2/colloquial | 300 | PASS |
| Rule | RQ2/defaultbait | 300 | PASS |
| Rule | RQ2/keyvalue | 300 | PASS |
| Rule | RQ2/negation | 300 | PASS |
| Rule | RQ2/noise | 300 | PASS |
| Rule | RQ2/revised | 300 | PASS |
| Rule | RQ3/F4_low | 300 | PASS |
| Rule | RQ3/F4_medium | 300 | PASS |
| Rule | RQ3/F4_high | 300 | PASS |
| Rule | RQ3/F6_low | 300 | PASS |
| Rule | RQ3/F6_medium | 300 | PASS |
| Rule | RQ3/F6_high | 300 | PASS |
| Rule | RQ3/F8_low | 300 | PASS |
| Rule | RQ3/F8_medium | 300 | PASS |
| Rule | RQ3/F8_high | 300 | PASS |
| MiniLM-Reranker | RQ4/K4 | 300 | PASS |
| MiniLM-Reranker | RQ4/K15 | 300 | PASS |
| MiniLM-Reranker | RQ4/K64 | 300 | PASS |
| MiniLM-Reranker | RQ4/K128 | 300 | PASS |
| MiniLM-Reranker | RQ4/K254 | 300 | PASS |
| MiniLM-Reranker | RQ4/churn25 | 300 | PASS |
| MiniLM-Reranker | RQ4/churn50 | 300 | PASS |
| DistilBERT-Clf-All | RQ4/K4 | 300 | PASS |
| DistilBERT-Clf-All | RQ4/K15 | 300 | PASS |
| DistilBERT-Clf-All | RQ4/K64 | 300 | PASS |
| DistilBERT-Clf-All | RQ4/K128 | 300 | PASS |
| DistilBERT-Clf-All | RQ4/K254 | 300 | PASS |
| DistilBERT-Clf-Frozen | RQ4/churn25 | 300 | PASS |
| DistilBERT-Clf-Frozen | RQ4/churn50 | 300 | PASS |
| DistilBERT-Clf-Retrained | RQ4/churn25 | 300 | PASS |
| DistilBERT-Clf-Retrained | RQ4/churn50 | 300 | PASS |

## 3. Oracle Positive Control Results

Per protocol, the Oracle interpreter must achieve EM 1.0 in every evaluated cell as a positive control.

| RQ | Condition | Oracle Rows | Oracle EM | Status |
|---|---|---|---|---|
| RQ1a | base | 300 | 1.0000 | PASS (1.000) |
| RQ1a | pad_512 | 300 | 1.0000 | PASS (1.000) |
| RQ1a | pad_2048 | 300 | 1.0000 | PASS (1.000) |
| RQ1a | pad_8192 | 300 | 1.0000 | PASS (1.000) |
| RQ1a | pad_16384 | 300 | 1.0000 | PASS (1.000) |
| RQ1b | k1 | 300 | 1.0000 | PASS (1.000) |
| RQ1b | k2 | 300 | 1.0000 | PASS (1.000) |
| RQ1b | k4 | 300 | 1.0000 | PASS (1.000) |
| RQ1b | k8 | 300 | 1.0000 | PASS (1.000) |
| RQ2 | clean | 300 | 1.0000 | PASS (1.000) |
| RQ2 | codeswitch | 300 | 1.0000 | PASS (1.000) |
| RQ2 | colloquial | 300 | 1.0000 | PASS (1.000) |
| RQ2 | defaultbait | 300 | 1.0000 | PASS (1.000) |
| RQ2 | keyvalue | 300 | 1.0000 | PASS (1.000) |
| RQ2 | negation | 300 | 1.0000 | PASS (1.000) |
| RQ2 | noise | 300 | 1.0000 | PASS (1.000) |
| RQ2 | revised | 300 | 1.0000 | PASS (1.000) |
| RQ3 | F4_low | 300 | 1.0000 | PASS (1.000) |
| RQ3 | F4_medium | 300 | 1.0000 | PASS (1.000) |
| RQ3 | F4_high | 300 | 1.0000 | PASS (1.000) |
| RQ3 | F6_low | 300 | 1.0000 | PASS (1.000) |
| RQ3 | F6_medium | 300 | 1.0000 | PASS (1.000) |
| RQ3 | F6_high | 300 | 1.0000 | PASS (1.000) |
| RQ3 | F8_low | 300 | 1.0000 | PASS (1.000) |
| RQ3 | F8_medium | 300 | 1.0000 | PASS (1.000) |
| RQ3 | F8_high | 300 | 1.0000 | PASS (1.000) |
| RQ4 | K4 | 0 | 0.0000 | **FLAG (EM=0.000, n=0)** |
| RQ4 | K15 | 0 | 0.0000 | **FLAG (EM=0.000, n=0)** |
| RQ4 | K64 | 0 | 0.0000 | **FLAG (EM=0.000, n=0)** |
| RQ4 | K128 | 0 | 0.0000 | **FLAG (EM=0.000, n=0)** |
| RQ4 | K254 | 0 | 0.0000 | **FLAG (EM=0.000, n=0)** |
| RQ4 | churn25 | 0 | 0.0000 | **FLAG (EM=0.000, n=0)** |
| RQ4 | churn50 | 0 | 0.0000 | **FLAG (EM=0.000, n=0)** |

## 4. Short Summary Tables by Research Question

### RQ1a: Input Length Scalability
| Condition | Model | EM | Valid | p50 (s) | p95 (s) |
| --- | --- | --- | --- | --- | --- |
| base | Jev-1.13.0 | 0.9400 | 1.0000 | 0.2736 | 0.3807 |
| base | DeepSeek-V4.1-Flash | 0.9900 | 1.0000 | 0.3777 | 1.0539 |
| base | GLM-5.3-Flash | 0.9867 | 1.0000 | 0.6464 | 2.6854 |
| base | Qwen3.8-Flash | 0.9600 | 0.9967 | 1.7743 | 3.6683 |
| base | SemIf-Qwen3.5-4B | 0.6400 | 1.0000 | 0.1237 | 0.2959 |
| base | Laya | 0.1100 | 1.0000 | 0.0548 | 0.2217 |
| base | Qwen3.5-4B-JSON | 0.4800 | 1.0000 | 0.7738 | 0.8679 |
| base | Rule | 0.0667 | 1.0000 | 0.0000 | 0.0000 |
| pad_512 | Jev-1.13.0 | 0.9233 | 1.0000 | 0.2757 | 0.3593 |
| pad_512 | DeepSeek-V4.1-Flash | 0.9733 | 1.0000 | 0.5027 | 0.8828 |
| pad_512 | GLM-5.3-Flash | 0.9733 | 1.0000 | 0.7200 | 2.4689 |
| pad_512 | Qwen3.8-Flash | 0.9633 | 0.9967 | 1.6432 | 4.5662 |
| pad_512 | SemIf-Qwen3.5-4B | 0.4300 | 1.0000 | 0.1298 | 0.2309 |
| pad_512 | Laya | 0.0100 | 1.0000 | 0.0618 | 0.1499 |
| pad_512 | Qwen3.5-4B-JSON | 0.4133 | 1.0000 | 0.7683 | 0.8719 |
| pad_512 | Rule | 0.0667 | 1.0000 | 0.0001 | 0.0001 |
| pad_2048 | Jev-1.13.0 | 0.9167 | 1.0000 | 0.2859 | 0.4037 |
| pad_2048 | DeepSeek-V4.1-Flash | 0.9733 | 1.0000 | 0.5573 | 1.0756 |
| pad_2048 | GLM-5.3-Flash | 0.9700 | 1.0000 | 0.6891 | 2.5184 |
| pad_2048 | Qwen3.8-Flash | 0.9700 | 1.0000 | 1.5937 | 2.4079 |
| pad_2048 | SemIf-Qwen3.5-4B | 0.4400 | 1.0000 | 0.2098 | 0.3341 |
| pad_2048 | Laya | 0.0133 | 1.0000 | 0.0728 | 0.0738 |
| pad_2048 | Qwen3.5-4B-JSON | 0.2967 | 1.0000 | 0.8568 | 0.9809 |
| pad_2048 | Rule | 0.0667 | 1.0000 | 0.0003 | 0.0004 |
| pad_8192 | Jev-1.13.0 | 0.9100 | 1.0000 | 0.3430 | 0.5252 |
| pad_8192 | DeepSeek-V4.1-Flash | 0.9767 | 1.0000 | 0.5187 | 0.7854 |
| pad_8192 | GLM-5.3-Flash | 0.9500 | 0.9933 | 1.1067 | 5.6310 |
| pad_8192 | Qwen3.8-Flash | 0.7633 | 1.0000 | 2.3641 | 4.7907 |
| pad_8192 | SemIf-Qwen3.5-4B | 0.4733 | 1.0000 | 0.6017 | 0.7179 |
| pad_8192 | Laya | 0.0233 | 1.0000 | 0.0928 | 0.0937 |
| pad_8192 | Qwen3.5-4B-JSON | 0.2167 | 1.0000 | 1.1398 | 1.2060 |
| pad_8192 | Rule | 0.0667 | 1.0000 | 0.0013 | 0.0017 |
| pad_16384 | Jev-1.13.0 | 0.9133 | 1.0000 | 0.4182 | 0.5234 |
| pad_16384 | DeepSeek-V4.1-Flash | 0.9733 | 1.0000 | 0.6383 | 1.0226 |
| pad_16384 | GLM-5.3-Flash | 0.9400 | 0.9800 | 1.5883 | 3.9389 |
| pad_16384 | Qwen3.8-Flash | 0.9600 | 1.0000 | 2.9205 | 4.2740 |
| pad_16384 | SemIf-Qwen3.5-4B | 0.4833 | 1.0000 | 1.1586 | 1.2377 |
| pad_16384 | Laya | 0.0167 | 1.0000 | 0.1368 | 0.1396 |
| pad_16384 | Qwen3.5-4B-JSON | 0.1800 | 1.0000 | 1.5497 | 1.6187 |
| pad_16384 | Rule | 0.0667 | 1.0000 | 0.0025 | 0.0038 |

### RQ1b: Batching & Bundle Scalability
| Condition | Model | Request EM | Msg EM | p50 (s) |
| --- | --- | --- | --- | --- |
| k1 | Jev-1.13.0 | 0.9533 | 0.9533 | 0.2721 |
| k1 | DeepSeek-V4.1-Flash | 0.9867 | 0.9867 | 0.3790 |
| k1 | GLM-5.3-Flash | 0.9833 | 0.9833 | 0.5828 |
| k1 | Qwen3.8-Flash | 0.9667 | 0.9667 | 1.3023 |
| k1 | SemIf-Qwen3.5-4B | 0.5933 | 0.5933 | 0.1208 |
| k1 | Laya | 0.0800 | 0.0800 | 0.0548 |
| k1 | Qwen3.5-4B-JSON | 0.4333 | 0.4333 | 0.7648 |
| k1 | Rule | 0.0667 | 0.0667 | 0.0000 |
| k2 | Jev-1.13.0 | 0.9483 | 0.8967 | 0.2761 |
| k2 | DeepSeek-V4.1-Flash | 0.9817 | 0.9633 | 0.4128 |
| k2 | GLM-5.3-Flash | 0.9367 | 0.9200 | 0.9661 |
| k2 | Qwen3.8-Flash | 0.9517 | 0.9033 | 1.7963 |
| k2 | SemIf-Qwen3.5-4B | 0.5133 | 0.2833 | 0.1367 |
| k2 | Laya | 0.0183 | 0.0000 | 0.0568 |
| k2 | Qwen3.5-4B-JSON | 0.4117 | 0.2233 | 1.1733 |
| k2 | Rule | 0.0667 | 0.0133 | 0.0000 |
| k4 | Jev-1.13.0 | 0.9567 | 0.8500 | 0.2784 |
| k4 | DeepSeek-V4.1-Flash | 0.9850 | 0.9400 | 0.5019 |
| k4 | GLM-5.3-Flash | 0.9825 | 0.9333 | 1.1396 |
| k4 | Qwen3.8-Flash | 0.9792 | 0.9267 | 2.5404 |
| k4 | SemIf-Qwen3.5-4B | 0.4008 | 0.0467 | 0.1977 |
| k4 | Laya | 0.0017 | 0.0000 | 0.0747 |
| k4 | Qwen3.5-4B-JSON | 0.4042 | 0.0533 | 2.1623 |
| k4 | Rule | 0.0667 | 0.0000 | 0.0001 |
| k8 | Jev-1.13.0 | 0.9554 | 0.7167 | 0.2905 |
| k8 | DeepSeek-V4.1-Flash | 0.9854 | 0.8867 | 0.8187 |
| k8 | GLM-5.3-Flash | 0.9833 | 0.8667 | 1.5597 |
| k8 | Qwen3.8-Flash | 0.9838 | 0.8800 | 3.7847 |
| k8 | SemIf-Qwen3.5-4B | 0.3013 | 0.0033 | 0.3481 |
| k8 | Laya | 0.0000 | 0.0000 | 0.1516 |
| k8 | Qwen3.5-4B-JSON | 0.4008 | 0.0200 | 4.1736 |
| k8 | Rule | 0.0667 | 0.0000 | 0.0001 |

### RQ2: Environmental & Syntactic Robustness
| Condition | Model | EM | Unsafe Rate | Valid |
| --- | --- | --- | --- | --- |
| clean | Jev-1.13.0 | 0.9500 | 0.0000 | 1.0000 |
| clean | DeepSeek-V4.1-Flash | 0.9867 | 0.0000 | 1.0000 |
| clean | GLM-5.3-Flash | 0.9933 | 0.0000 | 1.0000 |
| clean | Qwen3.8-Flash | 0.9600 | 0.0000 | 0.9967 |
| clean | SemIf-Qwen3.5-4B | 0.6400 | 0.0033 | 1.0000 |
| clean | Laya | 0.1100 | 0.1300 | 1.0000 |
| clean | Qwen3.5-4B-JSON | 0.4800 | 0.0000 | 1.0000 |
| clean | Rule | 0.0667 | 0.0000 | 1.0000 |
| codeswitch | Jev-1.13.0 | 0.9200 | 0.0000 | 1.0000 |
| codeswitch | DeepSeek-V4.1-Flash | 0.9833 | 0.0000 | 1.0000 |
| codeswitch | GLM-5.3-Flash | 0.9633 | 0.0033 | 1.0000 |
| codeswitch | Qwen3.8-Flash | 0.9633 | 0.0000 | 1.0000 |
| codeswitch | SemIf-Qwen3.5-4B | 0.5233 | 0.0033 | 0.9967 |
| codeswitch | Laya | 0.0667 | 0.1233 | 1.0000 |
| codeswitch | Qwen3.5-4B-JSON | 0.5267 | 0.0000 | 1.0000 |
| codeswitch | Rule | 0.0100 | 0.0000 | 1.0000 |
| colloquial | Jev-1.13.0 | 0.9367 | 0.0000 | 1.0000 |
| colloquial | DeepSeek-V4.1-Flash | 0.9900 | 0.0000 | 1.0000 |
| colloquial | GLM-5.3-Flash | 0.9767 | 0.0000 | 1.0000 |
| colloquial | Qwen3.8-Flash | 0.9567 | 0.0000 | 1.0000 |
| colloquial | SemIf-Qwen3.5-4B | 0.5000 | 0.0067 | 1.0000 |
| colloquial | Laya | 0.0967 | 0.0733 | 1.0000 |
| colloquial | Qwen3.5-4B-JSON | 0.4133 | 0.0000 | 1.0000 |
| colloquial | Rule | 0.0467 | 0.0000 | 1.0000 |
| defaultbait | Jev-1.13.0 | 0.6100 | 0.0433 | 1.0000 |
| defaultbait | DeepSeek-V4.1-Flash | 0.5300 | 0.0167 | 1.0000 |
| defaultbait | GLM-5.3-Flash | 0.6533 | 0.0167 | 1.0000 |
| defaultbait | Qwen3.8-Flash | 0.4700 | 0.0500 | 1.0000 |
| defaultbait | SemIf-Qwen3.5-4B | 0.3667 | 0.0200 | 1.0000 |
| defaultbait | Laya | 0.0633 | 0.1333 | 1.0000 |
| defaultbait | Qwen3.5-4B-JSON | 0.2767 | 0.0533 | 1.0000 |
| defaultbait | Rule | 0.0500 | 0.0067 | 1.0000 |
| keyvalue | Jev-1.13.0 | 0.9300 | 0.0000 | 1.0000 |
| keyvalue | DeepSeek-V4.1-Flash | 0.9867 | 0.0000 | 1.0000 |
| keyvalue | GLM-5.3-Flash | 0.9733 | 0.0000 | 1.0000 |
| keyvalue | Qwen3.8-Flash | 0.9500 | 0.0000 | 1.0000 |
| keyvalue | SemIf-Qwen3.5-4B | 0.6133 | 0.0000 | 1.0000 |
| keyvalue | Laya | 0.1100 | 0.0333 | 1.0000 |
| keyvalue | Qwen3.5-4B-JSON | 0.6100 | 0.0000 | 1.0000 |
| keyvalue | Rule | 0.0467 | 0.0000 | 1.0000 |
| negation | Jev-1.13.0 | 0.9233 | 0.0000 | 1.0000 |
| negation | DeepSeek-V4.1-Flash | 0.9733 | 0.0000 | 1.0000 |
| negation | GLM-5.3-Flash | 0.9100 | 0.0000 | 0.9633 |
| negation | Qwen3.8-Flash | 0.9567 | 0.0000 | 1.0000 |
| negation | SemIf-Qwen3.5-4B | 0.5200 | 0.0033 | 1.0000 |
| negation | Laya | 0.0900 | 0.0833 | 1.0000 |
| negation | Qwen3.5-4B-JSON | 0.4333 | 0.0000 | 1.0000 |
| negation | Rule | 0.0633 | 0.0000 | 1.0000 |
| noise | Jev-1.13.0 | 0.9300 | 0.0000 | 1.0000 |
| noise | DeepSeek-V4.1-Flash | 0.9700 | 0.0000 | 1.0000 |
| noise | GLM-5.3-Flash | 0.9333 | 0.0067 | 0.9733 |
| noise | Qwen3.8-Flash | 0.9467 | 0.0033 | 1.0000 |
| noise | SemIf-Qwen3.5-4B | 0.5567 | 0.0000 | 1.0000 |
| noise | Laya | 0.0967 | 0.1267 | 1.0000 |
| noise | Qwen3.5-4B-JSON | 0.4633 | 0.0000 | 1.0000 |
| noise | Rule | 0.0567 | 0.0000 | 1.0000 |
| revised | Jev-1.13.0 | 0.9467 | 0.0000 | 1.0000 |
| revised | DeepSeek-V4.1-Flash | 0.9900 | 0.0000 | 1.0000 |
| revised | GLM-5.3-Flash | 0.9667 | 0.0000 | 1.0000 |
| revised | Qwen3.8-Flash | 0.9867 | 0.0000 | 1.0000 |
| revised | SemIf-Qwen3.5-4B | 0.5267 | 0.0067 | 1.0000 |
| revised | Laya | 0.0800 | 0.1233 | 1.0000 |
| revised | Qwen3.5-4B-JSON | 0.5100 | 0.0000 | 1.0000 |
| revised | Rule | 0.0200 | 0.0033 | 1.0000 |

### RQ3: Schema & Field Scalability (F=4, 6, 8)
| Condition | Model | EM | Out Tok p50 | p50 (s) |
| --- | --- | --- | --- | --- |
| F4_low | Jev-1.13.0 | 0.9233 | 180.0000 | 0.2789 |
| F4_low | DeepSeek-V4.1-Flash | 0.9833 | 26.0000 | 0.4174 |
| F4_low | GLM-5.3-Flash | 0.8967 | 35.5000 | 0.9159 |
| F4_low | Qwen3.8-Flash | 0.9833 | 29.0000 | 1.2750 |
| F4_low | SemIf-Qwen3.5-4B | 0.5433 | 0.0000 | 0.1198 |
| F4_low | Laya | 0.2533 | 0.0000 | 0.0548 |
| F4_low | Qwen3.5-4B-JSON | 0.5300 | 30.0000 | 0.7658 |
| F4_low | Rule | 0.0400 | 0.0000 | 0.0000 |
| F4_medium | Jev-1.13.0 | 0.9567 | 180.0000 | 0.2785 |
| F4_medium | DeepSeek-V4.1-Flash | 0.9733 | 25.0000 | 0.3920 |
| F4_medium | GLM-5.3-Flash | 0.9867 | 35.0000 | 0.6454 |
| F4_medium | Qwen3.8-Flash | 0.9733 | 30.0000 | 1.3009 |
| F4_medium | SemIf-Qwen3.5-4B | 0.6033 | 0.0000 | 0.1198 |
| F4_medium | Laya | 0.2067 | 0.0000 | 0.0548 |
| F4_medium | Qwen3.5-4B-JSON | 0.6767 | 30.0000 | 0.7638 |
| F4_medium | Rule | 0.0500 | 0.0000 | 0.0000 |
| F4_high | Jev-1.13.0 | 0.9667 | 180.0000 | 0.2683 |
| F4_high | DeepSeek-V4.1-Flash | 0.9733 | 25.0000 | 0.3717 |
| F4_high | GLM-5.3-Flash | 0.9967 | 37.0000 | 0.6445 |
| F4_high | Qwen3.8-Flash | 0.9867 | 31.0000 | 1.3255 |
| F4_high | SemIf-Qwen3.5-4B | 0.6500 | 0.0000 | 0.1218 |
| F4_high | Laya | 0.1567 | 0.0000 | 0.0558 |
| F4_high | Qwen3.5-4B-JSON | 0.6767 | 30.0000 | 0.7666 |
| F4_high | Rule | 0.0500 | 0.0000 | 0.0000 |
| F6_low | Jev-1.13.0 | 0.7867 | 267.0000 | 0.2799 |
| F6_low | DeepSeek-V4.1-Flash | 0.9567 | 38.0000 | 0.4151 |
| F6_low | GLM-5.3-Flash | 0.9633 | 48.0000 | 0.7037 |
| F6_low | Qwen3.8-Flash | 0.9000 | 58.0000 | 1.7921 |
| F6_low | SemIf-Qwen3.5-4B | 0.4000 | 0.0000 | 0.1237 |
| F6_low | Laya | 0.0767 | 0.0000 | 0.0558 |
| F6_low | Qwen3.5-4B-JSON | 0.4833 | 45.0000 | 1.1055 |
| F6_low | Rule | 0.0033 | 0.0000 | 0.0000 |
| F6_medium | Jev-1.13.0 | 0.8400 | 267.0000 | 0.2680 |
| F6_medium | DeepSeek-V4.1-Flash | 0.9633 | 39.0000 | 0.4072 |
| F6_medium | GLM-5.3-Flash | 0.9467 | 50.0000 | 0.9232 |
| F6_medium | Qwen3.8-Flash | 0.9400 | 59.0000 | 1.5772 |
| F6_medium | SemIf-Qwen3.5-4B | 0.3367 | 0.0000 | 0.1228 |
| F6_medium | Laya | 0.0467 | 0.0000 | 0.0558 |
| F6_medium | Qwen3.5-4B-JSON | 0.4700 | 45.0000 | 1.1176 |
| F6_medium | Rule | 0.0067 | 0.0000 | 0.0000 |
| F6_high | Jev-1.13.0 | 0.7800 | 267.0000 | 0.2801 |
| F6_high | DeepSeek-V4.1-Flash | 0.9867 | 38.0000 | 0.4037 |
| F6_high | GLM-5.3-Flash | 0.9133 | 53.0000 | 0.8951 |
| F6_high | Qwen3.8-Flash | 0.9533 | 59.0000 | 1.8125 |
| F6_high | SemIf-Qwen3.5-4B | 0.3600 | 0.0000 | 0.1238 |
| F6_high | Laya | 0.0400 | 0.0000 | 0.0558 |
| F6_high | Qwen3.5-4B-JSON | 0.5233 | 44.0000 | 1.1120 |
| F6_high | Rule | 0.0000 | 0.0000 | 0.0000 |
| F8_low | Jev-1.13.0 | 0.5767 | 365.0000 | 0.2724 |
| F8_low | DeepSeek-V4.1-Flash | 0.9000 | 53.0000 | 0.4596 |
| F8_low | GLM-5.3-Flash | 0.8033 | 68.5000 | 0.9295 |
| F8_low | Qwen3.8-Flash | 0.8233 | 79.0000 | 2.0922 |
| F8_low | SemIf-Qwen3.5-4B | 0.1333 | 0.0000 | 0.1328 |
| F8_low | Laya | 0.0100 | 0.0000 | 0.0566 |
| F8_low | Qwen3.5-4B-JSON | 0.3000 | 63.0000 | 1.5070 |
| F8_low | Rule | 0.0000 | 0.0000 | 0.0000 |
| F8_medium | Jev-1.13.0 | 0.5667 | 364.0000 | 0.2721 |
| F8_medium | DeepSeek-V4.1-Flash | 0.9300 | 53.0000 | 0.4548 |
| F8_medium | GLM-5.3-Flash | 0.8367 | 71.0000 | 0.9831 |
| F8_medium | Qwen3.8-Flash | 0.7900 | 81.0000 | 1.8589 |
| F8_medium | SemIf-Qwen3.5-4B | 0.1000 | 0.0000 | 0.1338 |
| F8_medium | Laya | 0.0033 | 0.0000 | 0.0568 |
| F8_medium | Qwen3.5-4B-JSON | 0.2433 | 63.0000 | 1.5192 |
| F8_medium | Rule | 0.0000 | 0.0000 | 0.0000 |
| F8_high | Jev-1.13.0 | 0.5267 | 364.0000 | 0.2644 |
| F8_high | DeepSeek-V4.1-Flash | 0.9300 | 53.0000 | 0.4825 |
| F8_high | GLM-5.3-Flash | 0.8567 | 76.0000 | 1.2720 |
| F8_high | Qwen3.8-Flash | 0.6333 | 81.0000 | 1.9646 |
| F8_high | SemIf-Qwen3.5-4B | 0.0700 | 0.0000 | 0.1347 |
| F8_high | Laya | 0.0033 | 0.0000 | 0.0568 |
| F8_high | Qwen3.5-4B-JSON | 0.2100 | 63.0000 | 1.5472 |
| F8_high | Rule | 0.0000 | 0.0000 | 0.0000 |

### RQ4: Dynamic Catalog & Churn
| Condition | Model | Seen Top-1 | Unseen Top-1 | Unsupp F1 |
| --- | --- | --- | --- | --- |
| K4 | Jev-1.13.0 | 1.0000 |  | 0.8235 |
| K4 | DeepSeek-V4.1-Flash | 1.0000 |  | 0.8889 |
| K4 | GLM-5.3-Flash | 0.9889 |  | 0.9474 |
| K4 | Qwen3.8-Flash | 0.9963 |  | 0.8889 |
| K4 | SemIf-Qwen3.5-4B | 0.9963 |  | 0.8929 |
| K4 | Laya | 0.9815 |  | 0.3721 |
| K4 | Qwen3.5-4B-JSON | 1.0000 |  | 0.3784 |
| K4 | MiniLM-Reranker | 0.6519 |  | 0.3896 |
| K4 | DistilBERT-Clf-All | 0.8259 |  | 0.6364 |
| K15 | Jev-1.13.0 | 1.0000 |  | 0.8889 |
| K15 | DeepSeek-V4.1-Flash | 1.0000 |  | 1.0000 |
| K15 | GLM-5.3-Flash | 0.9889 |  | 0.9474 |
| K15 | Qwen3.8-Flash | 0.9963 |  | 0.9831 |
| K15 | SemIf-Qwen3.5-4B | 0.9852 |  | 0.9032 |
| K15 | Laya | 0.9148 |  | 0.0000 |
| K15 | Qwen3.5-4B-JSON | 0.9852 |  | 0.7234 |
| K15 | MiniLM-Reranker | 0.8370 |  | 0.5200 |
| K15 | DistilBERT-Clf-All | 0.8444 |  | 0.2800 |
| K64 | Jev-1.13.0 | 1.0000 |  | 0.7234 |
| K64 | DeepSeek-V4.1-Flash | 1.0000 |  | 0.9286 |
| K64 | GLM-5.3-Flash | 1.0000 |  | 0.9474 |
| K64 | Qwen3.8-Flash | 1.0000 |  | 0.9286 |
| K64 | SemIf-Qwen3.5-4B | 0.0000 |  | 0.0000 |
| K64 | Laya | 0.5704 |  | 0.0645 |
| K64 | Qwen3.5-4B-JSON | 0.9519 |  | 0.6222 |
| K64 | MiniLM-Reranker | 0.8852 |  | 0.5333 |
| K64 | DistilBERT-Clf-All | 0.6259 |  | 0.2500 |
| K128 | Jev-1.13.0 | 1.0000 | 1.0000 | 0.7234 |
| K128 | DeepSeek-V4.1-Flash | 1.0000 | 1.0000 | 0.9474 |
| K128 | GLM-5.3-Flash | 1.0000 | 1.0000 | 0.9091 |
| K128 | Qwen3.8-Flash | 1.0000 | 1.0000 | 0.8889 |
| K128 | SemIf-Qwen3.5-4B | 0.0000 | 0.0000 | 0.0000 |
| K128 | Laya | 0.2985 | 0.4485 | 0.0000 |
| K128 | Qwen3.5-4B-JSON | 1.0000 | 0.9779 | 0.8235 |
| K128 | MiniLM-Reranker | 0.8955 | 0.9265 | 0.5532 |
| K128 | DistilBERT-Clf-All | 0.5896 | 0.2647 | 0.1515 |
| K254 | Jev-1.13.0 | 1.0000 | 1.0000 | 0.9286 |
| K254 | DeepSeek-V4.1-Flash | 1.0000 | 0.9951 | 1.0000 |
| K254 | GLM-5.3-Flash | 1.0000 | 1.0000 | 1.0000 |
| K254 | Qwen3.8-Flash | 0.9851 | 1.0000 | 0.9831 |
| K254 | SemIf-Qwen3.5-4B | 0.0000 | 0.0000 | 0.0000 |
| K254 | Laya | 0.0000 | 0.0000 | 0.0000 |
| K254 | Qwen3.5-4B-JSON | 0.8955 | 0.9212 | 0.9333 |
| K254 | MiniLM-Reranker | 0.8657 | 0.8719 | 0.7500 |
| K254 | DistilBERT-Clf-All | 0.6269 | 0.1379 | 0.5361 |
| churn25 | Jev-1.13.0 | 1.0000 | 1.0000 | 0.7500 |
| churn25 | DeepSeek-V4.1-Flash | 1.0000 | 1.0000 | 1.0000 |
| churn25 | GLM-5.3-Flash | 1.0000 | 1.0000 | 0.9474 |
| churn25 | Qwen3.8-Flash | 1.0000 | 1.0000 | 0.9831 |
| churn25 | SemIf-Qwen3.5-4B | 0.0000 | 0.0000 | 0.0000 |
| churn25 | Laya | 0.5644 | 0.6176 | 0.0000 |
| churn25 | Qwen3.5-4B-JSON | 0.9802 | 1.0000 | 0.5714 |
| churn25 | MiniLM-Reranker | 0.8911 | 0.9412 | 0.2800 |
| churn25 | DistilBERT-Clf-Frozen | 0.6535 | 0.0000 | 0.2656 |
| churn25 | DistilBERT-Clf-Retrained | 0.7079 | 0.1471 | 0.2574 |
| churn50 | Jev-1.13.0 | 1.0000 | 1.0000 | 0.8000 |
| churn50 | DeepSeek-V4.1-Flash | 1.0000 | 1.0000 | 0.9474 |
| churn50 | GLM-5.3-Flash | 1.0000 | 1.0000 | 0.9831 |
| churn50 | Qwen3.8-Flash | 1.0000 | 1.0000 | 0.9655 |
| churn50 | SemIf-Qwen3.5-4B | 0.0000 | 0.0000 | 0.0000 |
| churn50 | Laya | 0.5882 | 0.6716 | 0.0000 |
| churn50 | Qwen3.5-4B-JSON | 0.9706 | 0.9851 | 0.7755 |
| churn50 | MiniLM-Reranker | 0.8309 | 0.9328 | 0.5075 |
| churn50 | DistilBERT-Clf-Frozen | 0.5221 | 0.0000 | 0.2378 |
| churn50 | DistilBERT-Clf-Retrained | 0.4412 | 0.1418 | 0.2308 |

## 5. Communications-Community Metrics Summary (Addendum A1)

Descriptive statistics aligned with communications/networking venues (availability, SLA violation, jitter, single-client throughput, goodput, energy):

| Model | RQ/Cond | Avail | SLA Viol | Tput (dec/s) | Goodput (corr/s) | Jitter IQR (s) | Energy (J/dec) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Jev-1.13.0 | RQ1a/base | 1.000 | 0.000 | 3.47 | 3.26 | 0.0656 | - |
| DeepSeek-V4.1-Flash | RQ1a/base | 1.000 | 0.003 | 1.87 | 1.85 | 0.0710 | - |
| GLM-5.3-Flash | RQ1a/base | 1.000 | 0.007 | 1.05 | 1.04 | 0.2934 | - |
| Qwen3.8-Flash | RQ1a/base | 0.997 | 0.003 | 0.48 | 0.46 | 0.9019 | - |
| SemIf-Qwen3.5-4B | RQ1a/base | 1.000 | 0.080 | 6.78 | 4.34 | 0.0010 | 23.68 |
| Laya | RQ1a/base | 1.000 | 0.143 | 12.74 | 1.40 | 0.0009 | 8.38 |
| Qwen3.5-4B-JSON | RQ1a/base | 1.000 | 0.053 | 1.26 | 0.60 | 0.0482 | 127.19 |
| Rule | RQ1a/base | 1.000 | 0.880 | 50070.33 | 3338.02 | 0.0000 | - |
| Jev-1.13.0 | RQ1a/pad_512 | 1.000 | 0.010 | 3.46 | 3.19 | 0.0558 | - |
| DeepSeek-V4.1-Flash | RQ1a/pad_512 | 1.000 | 0.007 | 1.73 | 1.68 | 0.1086 | - |
| GLM-5.3-Flash | RQ1a/pad_512 | 1.000 | 0.017 | 0.93 | 0.91 | 0.2549 | - |
| Qwen3.8-Flash | RQ1a/pad_512 | 0.997 | 0.003 | 0.49 | 0.47 | 0.9228 | - |
| SemIf-Qwen3.5-4B | RQ1a/pad_512 | 1.000 | 0.307 | 6.99 | 3.01 | 0.0020 | 30.89 |
| Laya | RQ1a/pad_512 | 1.000 | 0.307 | 14.36 | 0.14 | 0.0020 | 11.63 |
| Qwen3.5-4B-JSON | RQ1a/pad_512 | 1.000 | 0.057 | 1.29 | 0.53 | 0.0669 | 130.52 |
| Rule | RQ1a/pad_512 | 1.000 | 0.880 | 11612.81 | 774.19 | 0.0001 | - |
| Jev-1.13.0 | RQ1a/pad_2048 | 1.000 | 0.010 | 3.31 | 3.04 | 0.0535 | - |
| DeepSeek-V4.1-Flash | RQ1a/pad_2048 | 1.000 | 0.003 | 1.09 | 1.06 | 0.1615 | - |
| GLM-5.3-Flash | RQ1a/pad_2048 | 1.000 | 0.017 | 1.04 | 1.01 | 0.2716 | - |
| Qwen3.8-Flash | RQ1a/pad_2048 | 1.000 | 0.000 | 0.58 | 0.56 | 0.3516 | - |
| SemIf-Qwen3.5-4B | RQ1a/pad_2048 | 1.000 | 0.327 | 4.36 | 1.92 | 0.0011 | 61.58 |
| Laya | RQ1a/pad_2048 | 1.000 | 0.507 | 13.68 | 0.18 | 0.0009 | 14.38 |
| Qwen3.5-4B-JSON | RQ1a/pad_2048 | 1.000 | 0.077 | 1.14 | 0.34 | 0.0305 | 161.97 |
| Rule | RQ1a/pad_2048 | 1.000 | 0.880 | 3283.48 | 218.90 | 0.0002 | - |
| Jev-1.13.0 | RQ1a/pad_8192 | 1.000 | 0.017 | 2.64 | 2.41 | 0.0723 | - |
| DeepSeek-V4.1-Flash | RQ1a/pad_8192 | 1.000 | 0.003 | 1.78 | 1.73 | 0.1162 | - |
| GLM-5.3-Flash | RQ1a/pad_8192 | 0.993 | 0.030 | 0.48 | 0.45 | 0.4746 | - |
| Qwen3.8-Flash | RQ1a/pad_8192 | 1.000 | 0.213 | 0.37 | 0.28 | 0.6829 | - |
| SemIf-Qwen3.5-4B | RQ1a/pad_8192 | 1.000 | 0.333 | 1.61 | 0.76 | 0.0079 | 194.92 |
| Laya | RQ1a/pad_8192 | 1.000 | 0.497 | 10.78 | 0.25 | 0.0000 | 16.28 |
| Qwen3.5-4B-JSON | RQ1a/pad_8192 | 1.000 | 0.100 | 0.86 | 0.19 | 0.0243 | 279.80 |
| Rule | RQ1a/pad_8192 | 1.000 | 0.880 | 859.91 | 57.33 | 0.0009 | - |
| Jev-1.13.0 | RQ1a/pad_16384 | 1.000 | 0.013 | 2.07 | 1.89 | 0.0550 | - |
| DeepSeek-V4.1-Flash | RQ1a/pad_16384 | 1.000 | 0.003 | 1.43 | 1.40 | 0.1700 | - |
| GLM-5.3-Flash | RQ1a/pad_16384 | 0.980 | 0.050 | 0.47 | 0.44 | 0.8289 | - |

## Flagged cells

Per analysis plan ("Cells with valid rate < 50% are still tested (no screening), and flagged"): 

- **SemIf-Qwen3.5-4B** (RQ4/K64): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "Question 'r1__service_type' has 65 options; SemIf supports 2-16 options"
- **SemIf-Qwen3.5-4B** (RQ4/K128): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "Question 'r1__service_type' has 129 options; SemIf supports 2-16 options"
- **SemIf-Qwen3.5-4B** (RQ4/K254): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "Question 'r1__service_type' has 255 options; SemIf supports 2-16 options"
- **Laya** (RQ4/K254): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "question 'r1__service_type' options exceed head_max_len=256"
- **SemIf-Qwen3.5-4B** (RQ4/churn25): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "Question 'r1__service_type' has 65 options; SemIf supports 2-16 options"
- **SemIf-Qwen3.5-4B** (RQ4/churn50): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "Question 'r1__service_type' has 65 options; SemIf supports 2-16 options"
