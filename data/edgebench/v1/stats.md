# EdgeIntent v1 Corpus Statistics

| Condition | Split | N | Length p5 | Length p50 | Length p95 | First-pass yield | Final yield |
|---|---|---|---|---|---|---|---|
| RQ1a/base | test | 300 | 24.0 | 38.0 | 64.0 | n/a | n/a |
| RQ1a/base | dev | 60 | 33.0 | 46.0 | 66.0 | n/a | n/a |
| RQ1a/pad_16384 | test | 300 | 16382.0 | 16383.0 | 16384.0 | n/a | n/a |
| RQ1a/pad_16384 | dev | 60 | 16382.0 | 16383.5 | 16384.0 | n/a | n/a |
| RQ1a/pad_2048 | test | 300 | 2046.0 | 2047.0 | 2048.0 | n/a | n/a |
| RQ1a/pad_2048 | dev | 60 | 2046.0 | 2047.0 | 2048.0 | n/a | n/a |
| RQ1a/pad_512 | test | 300 | 510.0 | 511.0 | 512.0 | n/a | n/a |
| RQ1a/pad_512 | dev | 60 | 510.0 | 511.0 | 512.0 | n/a | n/a |
| RQ1a/pad_8192 | test | 300 | 8190.0 | 8191.0 | 8192.0 | n/a | n/a |
| RQ1a/pad_8192 | dev | 60 | 8190.9 | 8191.0 | 8192.0 | n/a | n/a |
| RQ1b/k1 | test | 300 | 28.0 | 42.0 | 68.0 | n/a | n/a |
| RQ1b/k1 | dev | 60 | 37.0 | 50.0 | 70.0 | n/a | n/a |
| RQ1b/k2 | test | 300 | 66.0 | 87.0 | 123.0 | n/a | n/a |
| RQ1b/k2 | dev | 60 | 82.0 | 103.0 | 125.0 | n/a | n/a |
| RQ1b/k4 | test | 300 | 149.0 | 177.0 | 223.0 | n/a | n/a |
| RQ1b/k4 | dev | 60 | 175.7 | 201.5 | 242.0 | n/a | n/a |
| RQ1b/k8 | test | 300 | 302.9 | 356.0 | 432.0 | n/a | n/a |
| RQ1b/k8 | dev | 60 | 356.9 | 410.5 | 458.5 | n/a | n/a |
| RQ2/clean | test | 300 | 24.0 | 38.0 | 64.0 | 100.0% | 100.0% |
| RQ2/clean | dev | 60 | 33.0 | 46.0 | 66.0 | 100.0% | 100.0% |
| RQ2/codeswitch | test | 300 | 30.0 | 43.0 | 68.1 | 93.3% | 100.0% |
| RQ2/codeswitch | dev | 60 | 37.0 | 56.0 | 84.1 | 93.3% | 100.0% |
| RQ2/colloquial | test | 300 | 25.0 | 41.0 | 69.0 | 100.0% | 100.0% |
| RQ2/colloquial | dev | 60 | 37.0 | 48.5 | 71.0 | 100.0% | 100.0% |
| RQ2/defaultbait | test | 300 | 33.0 | 44.0 | 69.0 | 90.0% | 100.0% |
| RQ2/defaultbait | dev | 60 | 43.0 | 56.0 | 80.0 | 90.0% | 100.0% |
| RQ2/keyvalue | test | 300 | 14.0 | 27.0 | 53.0 | 99.7% | 100.0% |
| RQ2/keyvalue | dev | 60 | 26.9 | 41.5 | 65.0 | 99.7% | 100.0% |
| RQ2/negation | test | 300 | 30.0 | 45.0 | 69.1 | 100.0% | 100.0% |
| RQ2/negation | dev | 60 | 35.9 | 53.0 | 81.0 | 100.0% | 100.0% |
| RQ2/noise | test | 300 | 24.0 | 38.0 | 66.0 | n/a | n/a |
| RQ2/noise | dev | 60 | 32.8 | 44.0 | 65.2 | n/a | n/a |
| RQ2/revised | test | 300 | 31.0 | 46.0 | 79.1 | 99.4% | 100.0% |
| RQ2/revised | dev | 60 | 50.0 | 63.0 | 84.1 | 99.4% | 100.0% |
| RQ3/F4_high | test | 300 | 61.0 | 77.5 | 108.0 | 100.0% | 100.0% |
| RQ3/F4_high | dev | 60 | 53.0 | 64.5 | 79.0 | 100.0% | 100.0% |
| RQ3/F4_low | test | 300 | 21.0 | 37.5 | 65.0 | 99.7% | 100.0% |
| RQ3/F4_low | dev | 60 | 32.0 | 48.0 | 70.2 | 99.7% | 100.0% |
| RQ3/F4_medium | test | 300 | 36.0 | 51.0 | 72.1 | 100.0% | 100.0% |
| RQ3/F4_medium | dev | 60 | 44.0 | 56.0 | 81.0 | 100.0% | 100.0% |
| RQ3/F6_high | test | 300 | 67.0 | 81.0 | 108.0 | 98.3% | 100.0% |
| RQ3/F6_high | dev | 60 | 68.8 | 81.0 | 104.1 | 98.3% | 100.0% |
| RQ3/F6_low | test | 300 | 33.0 | 50.0 | 76.1 | 100.0% | 100.0% |
| RQ3/F6_low | dev | 60 | 35.0 | 46.5 | 64.0 | 100.0% | 100.0% |
| RQ3/F6_medium | test | 300 | 46.0 | 61.0 | 90.0 | 97.8% | 100.0% |
| RQ3/F6_medium | dev | 60 | 56.9 | 68.5 | 96.0 | 97.8% | 100.0% |
| RQ3/F8_high | test | 300 | 68.0 | 87.0 | 124.0 | 100.0% | 100.0% |
| RQ3/F8_high | dev | 60 | 76.0 | 89.5 | 128.0 | 100.0% | 100.0% |
| RQ3/F8_low | test | 300 | 29.0 | 41.0 | 77.0 | 98.3% | 100.0% |
| RQ3/F8_low | dev | 60 | 44.0 | 63.0 | 81.1 | 98.3% | 100.0% |
| RQ3/F8_medium | test | 300 | 46.0 | 65.0 | 101.1 | 98.9% | 100.0% |
| RQ3/F8_medium | dev | 60 | 46.9 | 67.0 | 83.2 | 98.9% | 100.0% |
| RQ4/K128 | test | 300 | 36.0 | 54.5 | 78.0 | 97.8% | 100.0% |
| RQ4/K128 | dev | 60 | 39.9 | 55.5 | 72.1 | 97.8% | 100.0% |
| RQ4/K15 | test | 300 | 33.0 | 52.0 | 82.1 | 97.8% | 100.0% |
| RQ4/K15 | dev | 60 | 29.9 | 45.5 | 66.1 | 97.8% | 100.0% |
| RQ4/K254 | test | 300 | 34.0 | 51.0 | 75.1 | 99.2% | 100.0% |
| RQ4/K254 | dev | 60 | 50.0 | 65.5 | 91.1 | 99.2% | 100.0% |
| RQ4/K4 | test | 300 | 27.0 | 46.0 | 76.0 | 97.5% | 100.0% |
| RQ4/K4 | dev | 60 | 27.9 | 44.0 | 63.0 | 97.5% | 100.0% |
| RQ4/K64 | test | 300 | 38.0 | 55.0 | 81.1 | 99.7% | 100.0% |
| RQ4/K64 | dev | 60 | 34.0 | 57.0 | 75.0 | 99.7% | 100.0% |
| RQ4/churn25 | test | 300 | 35.0 | 53.0 | 81.0 | 98.9% | 100.0% |
| RQ4/churn25 | dev | 60 | 33.0 | 44.0 | 66.1 | 98.9% | 100.0% |
| RQ4/churn50 | test | 300 | 35.0 | 56.0 | 83.1 | 99.2% | 100.0% |
| RQ4/churn50 | dev | 60 | 30.9 | 45.0 | 64.0 | 99.2% | 100.0% |

## Field Marginals per Condition

### RQ1a/base (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ1a/base (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ1a/pad_16384 (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ1a/pad_16384 (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ1a/pad_2048 (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ1a/pad_2048 (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ1a/pad_512 (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ1a/pad_512 (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ1a/pad_8192 (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ1a/pad_8192 (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ1b/k1 (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ1b/k1 (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ1b/k2 (test, n=300)

- **service_type**: count: 200, detection: 200, ocr: 200
- **locality**: remote_allowed: 158, site_only: 158, unspecified: 284
- **quality_floor**: high: 158, standard: 158, unspecified: 284
- **urgency**: normal: 158, unspecified: 282, urgent: 160

### RQ1b/k2 (dev, n=60)

- **service_type**: count: 40, detection: 40, ocr: 40
- **locality**: remote_allowed: 32, site_only: 32, unspecified: 56
- **quality_floor**: high: 34, standard: 30, unspecified: 56
- **urgency**: normal: 32, unspecified: 56, urgent: 32

### RQ1b/k4 (test, n=300)

- **service_type**: count: 400, detection: 400, ocr: 400
- **locality**: remote_allowed: 316, site_only: 316, unspecified: 568
- **quality_floor**: high: 316, standard: 316, unspecified: 568
- **urgency**: normal: 316, unspecified: 564, urgent: 320

### RQ1b/k4 (dev, n=60)

- **service_type**: count: 80, detection: 80, ocr: 80
- **locality**: remote_allowed: 64, site_only: 64, unspecified: 112
- **quality_floor**: high: 68, standard: 60, unspecified: 112
- **urgency**: normal: 64, unspecified: 112, urgent: 64

### RQ1b/k8 (test, n=300)

- **service_type**: count: 800, detection: 800, ocr: 800
- **locality**: remote_allowed: 632, site_only: 632, unspecified: 1136
- **quality_floor**: high: 632, standard: 632, unspecified: 1136
- **urgency**: normal: 632, unspecified: 1128, urgent: 640

### RQ1b/k8 (dev, n=60)

- **service_type**: count: 160, detection: 160, ocr: 160
- **locality**: remote_allowed: 128, site_only: 128, unspecified: 224
- **quality_floor**: high: 136, standard: 120, unspecified: 224
- **urgency**: normal: 128, unspecified: 224, urgent: 128

### RQ2/clean (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ2/clean (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ2/codeswitch (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ2/codeswitch (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ2/colloquial (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ2/colloquial (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ2/defaultbait (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ2/defaultbait (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ2/keyvalue (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ2/keyvalue (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ2/negation (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ2/negation (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ2/noise (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ2/noise (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ2/revised (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 79, site_only: 79, unspecified: 142
- **quality_floor**: high: 79, standard: 79, unspecified: 142
- **urgency**: normal: 79, unspecified: 141, urgent: 80

### RQ2/revised (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 16, site_only: 16, unspecified: 28
- **quality_floor**: high: 17, standard: 15, unspecified: 28
- **urgency**: normal: 16, unspecified: 28, urgent: 16

### RQ3/F4_high (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100

### RQ3/F4_high (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20

### RQ3/F4_low (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100

### RQ3/F4_low (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20

### RQ3/F4_medium (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100

### RQ3/F4_medium (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20

### RQ3/F6_high (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100
- **retention**: discard_after_use: 100, retain_allowed: 100, unspecified: 100
- **energy**: eco: 100, performance: 100, unspecified: 100

### RQ3/F6_high (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20
- **retention**: discard_after_use: 20, retain_allowed: 20, unspecified: 20
- **energy**: eco: 20, performance: 20, unspecified: 20

### RQ3/F6_low (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100
- **retention**: discard_after_use: 100, retain_allowed: 100, unspecified: 100
- **energy**: eco: 100, performance: 100, unspecified: 100

### RQ3/F6_low (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20
- **retention**: discard_after_use: 20, retain_allowed: 20, unspecified: 20
- **energy**: eco: 20, performance: 20, unspecified: 20

### RQ3/F6_medium (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100
- **retention**: discard_after_use: 100, retain_allowed: 100, unspecified: 100
- **energy**: eco: 100, performance: 100, unspecified: 100

### RQ3/F6_medium (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20
- **retention**: discard_after_use: 20, retain_allowed: 20, unspecified: 20
- **energy**: eco: 20, performance: 20, unspecified: 20

### RQ3/F8_high (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100
- **retention**: discard_after_use: 100, retain_allowed: 100, unspecified: 100
- **energy**: eco: 100, performance: 100, unspecified: 100
- **redundancy**: replicated: 100, single: 100, unspecified: 100
- **latency_class**: batch: 75, interactive: 75, realtime: 75, unspecified: 75

### RQ3/F8_high (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20
- **retention**: discard_after_use: 20, retain_allowed: 20, unspecified: 20
- **energy**: eco: 20, performance: 20, unspecified: 20
- **redundancy**: replicated: 20, single: 20, unspecified: 20
- **latency_class**: batch: 15, interactive: 15, realtime: 15, unspecified: 15

### RQ3/F8_low (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100
- **retention**: discard_after_use: 100, retain_allowed: 100, unspecified: 100
- **energy**: eco: 100, performance: 100, unspecified: 100
- **redundancy**: replicated: 100, single: 100, unspecified: 100
- **latency_class**: batch: 75, interactive: 75, realtime: 75, unspecified: 75

### RQ3/F8_low (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20
- **retention**: discard_after_use: 20, retain_allowed: 20, unspecified: 20
- **energy**: eco: 20, performance: 20, unspecified: 20
- **redundancy**: replicated: 20, single: 20, unspecified: 20
- **latency_class**: batch: 15, interactive: 15, realtime: 15, unspecified: 15

### RQ3/F8_medium (test, n=300)

- **service_type**: count: 100, detection: 100, ocr: 100
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100
- **retention**: discard_after_use: 100, retain_allowed: 100, unspecified: 100
- **energy**: eco: 100, performance: 100, unspecified: 100
- **redundancy**: replicated: 100, single: 100, unspecified: 100
- **latency_class**: batch: 75, interactive: 75, realtime: 75, unspecified: 75

### RQ3/F8_medium (dev, n=60)

- **service_type**: count: 20, detection: 20, ocr: 20
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20
- **retention**: discard_after_use: 20, retain_allowed: 20, unspecified: 20
- **energy**: eco: 20, performance: 20, unspecified: 20
- **redundancy**: replicated: 20, single: 20, unspecified: 20
- **latency_class**: batch: 15, interactive: 15, realtime: 15, unspecified: 15

### RQ4/K128 (test, n=300)

- **service_type**: air_quality_pm25_analyzer: 2, ambient_noise_level_meter: 2, animal_detector: 2, ar_marker_bundle_adjuster: 2, audio_downsampling_resampler: 2, audio_flac_to_opus_compressor: 2, audio_guide_multilingual_synthesizer: 2, bank_check_micr_parser: 3, bgp_route_leak_detector: 2, billboard_text_ocr: 3, biometric_fingerprint_reader: 2, bridge_overheight_vehicle_detector: 2, bus_lane_encroachment_detector: 2, business_card_ocr: 3, camera_tamper_detector: 2, car_alarm_detector: 2, cart_abandonment_tracker: 2, chat_message_translator: 2, co2_indoor_ventilation_monitor: 3, construction_activity_analyzer: 2, container_stack_counter: 2, conveyor_belt_tear_inspector: 2, coronary_calcium_ct_triage: 2, count: 2, crosswalk_jaywalking_detector: 2, crowd_head_counter: 2, crowd_surge_detector: 2, ct_brain_hemorrhage_triage: 2, customs_declaration_parser: 2, ddos_syn_flood_detector: 2, dense_depth_map_completer: 2, detection: 3, dicom_medical_image_compressor: 2, drone_acoustic_classifier: 2, drone_perimeter_alert: 2, emergency_siren_detector: 3, en_to_ja_menu_translator: 2, en_to_zh_subtitle_generator: 2, endcap_promotional_gaze_tracker: 2, eye_gaze_direction_tracker: 2, facial_blendshape_animator: 2, fence_climbing_detector: 2, fitting_room_occupancy_sensor: 2, fr_to_en_document_translator: 3, fundus_diabetic_retinopathy_triage: 2, gaussian_splat_renderer: 2, geotiff_raster_compressor: 2, grab_and_go_basket_tracker: 2, h264_bitrate_downscaler: 2, hand_mesh_pose_tracker: 2, handwritten_form_ocr: 2, hazard_cone_detector: 2, hdr_to_sdr_tone_mapper: 2, hov_lane_occupancy_verifier: 2, industrial_bearing_monitor: 2, insurance_claim_form_parser: 2, interface_flapping_detector: 2, ip_fragmentation_attack_detector: 2, ja_to_en_menu_translator: 3, json_to_protobuf_serializer: 2, label_alignment_inspector: 2, legal_contract_clause_tagger: 2, loitering_detector: 2, loss_prevention_sweethearting_detector: 2, luggage_counter: 2, mammogram_mass_triage: 2, medical_prescription_parser: 2, noise_pollution_monitor: 2, occlusion_culling_optimizer: 2, ocr: 3, package_xray_contraband_screener: 2, packet_jitter_analyzer: 2, paint_scratch_inspector: 3, pallet_counter: 2, parking_spot_counter: 2, parquet_columnar_encoder: 2, passport_mrz_ocr: 2, pcb_solder_bridge_inspector: 2, pothole_road_surface_scanner: 2, ppe_detector: 2, prescription_label_ocr: 2, produce_ripeness_scanner: 2, product_unit_counter: 2, puddle_detector: 3, purchase_order_matcher: 2, queue_length_analyzer: 2, radiation_geiger_counter_monitor: 2, refrigeration_temperature_compliance_logger: 2, retinal_oct_macular_edema_triage: 2, rogue_dhcp_server_detector: 2, roundabout_gap_analyzer: 2, rubber_o_ring_flaw_inspector: 2, runway_incursion_detector: 2, school_zone_speed_monitor: 2, secure_server_rack_door_monitor: 3, self_checkout_item_mismatch_detector: 2, shadow_map_projector: 2, sheet_metal_burr_inspector: 2, shelf_out_of_stock_detector: 2, shipping_label_ocr: 2, shipping_manifest_digitizer: 2, skin_lesion_melanoma_triage: 2, solar_cell_microcrack_inspector: 2, solar_panel_counter: 2, speaker_diarization: 2, speech_to_text: 3, stroke_mri_diffusion_triage: 3, tailgating_access_interceptor: 2, tcp_retransmission_monitor: 2, technical_terminology_normalizer: 2, threaded_screw_inspector: 2, tls_fingerprint_classifier: 2, traffic_incident_detector: 2, unattended_baggage_detector: 2, under_vehicle_inspection_scanner: 2, unsupported: 30, utility_bill_parser: 2, uv_index_solar_radiometer: 2, vehicle_detector: 2, vin_ocr: 2, visitor_id_scanner: 2, wake_word_spotter: 2, water_turbidity_clarity_meter: 2, weapon_detector: 2, wildfire_thermal_hotspot_detector: 2, work_zone_merge_compliance_monitor: 2, wrist_scaphoid_fracture_triage: 2, wrong_way_driver_detector: 2, zh_to_en_subtitle_generator: 2
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100

### RQ4/K128 (dev, n=60)

- **service_type**: animal_detector: 1, ar_marker_bundle_adjuster: 1, audio_flac_to_opus_compressor: 1, audio_guide_multilingual_synthesizer: 1, billboard_text_ocr: 1, bridge_overheight_vehicle_detector: 1, bus_lane_encroachment_detector: 1, construction_activity_analyzer: 1, conveyor_belt_tear_inspector: 1, count: 1, crosswalk_jaywalking_detector: 1, ct_brain_hemorrhage_triage: 1, customs_declaration_parser: 1, ddos_syn_flood_detector: 1, detection: 1, drone_acoustic_classifier: 1, en_to_ja_menu_translator: 1, endcap_promotional_gaze_tracker: 1, fence_climbing_detector: 1, grab_and_go_basket_tracker: 1, h264_bitrate_downscaler: 1, insurance_claim_form_parser: 1, interface_flapping_detector: 1, json_to_protobuf_serializer: 1, loitering_detector: 1, mammogram_mass_triage: 1, noise_pollution_monitor: 1, occlusion_culling_optimizer: 1, packet_jitter_analyzer: 1, pcb_solder_bridge_inspector: 1, pothole_road_surface_scanner: 1, product_unit_counter: 1, radiation_geiger_counter_monitor: 1, refrigeration_temperature_compliance_logger: 1, rubber_o_ring_flaw_inspector: 1, school_zone_speed_monitor: 1, shadow_map_projector: 1, shelf_out_of_stock_detector: 1, shipping_label_ocr: 1, shipping_manifest_digitizer: 1, solar_panel_counter: 1, speaker_diarization: 1, tailgating_access_interceptor: 1, tcp_retransmission_monitor: 1, tls_fingerprint_classifier: 1, traffic_incident_detector: 1, unsupported: 6, uv_index_solar_radiometer: 1, vin_ocr: 1, visitor_id_scanner: 1, water_turbidity_clarity_meter: 1, weapon_detector: 1, work_zone_merge_compliance_monitor: 1, wrist_scaphoid_fracture_triage: 1, zh_to_en_subtitle_generator: 1
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20

### RQ4/K15 (test, n=300)

- **service_type**: air_quality_pm25_analyzer: 18, ar_marker_bundle_adjuster: 18, count: 18, detection: 18, fence_climbing_detector: 18, fitting_room_occupancy_sensor: 18, insurance_claim_form_parser: 18, ja_to_en_menu_translator: 18, json_to_protobuf_serializer: 18, ocr: 18, roundabout_gap_analyzer: 18, runway_incursion_detector: 18, solar_cell_microcrack_inspector: 18, tcp_retransmission_monitor: 18, unsupported: 30, wrist_scaphoid_fracture_triage: 18
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100

### RQ4/K15 (dev, n=60)

- **service_type**: air_quality_pm25_analyzer: 4, ar_marker_bundle_adjuster: 4, count: 4, detection: 4, fence_climbing_detector: 3, fitting_room_occupancy_sensor: 3, insurance_claim_form_parser: 4, ja_to_en_menu_translator: 3, json_to_protobuf_serializer: 3, ocr: 4, roundabout_gap_analyzer: 4, runway_incursion_detector: 3, solar_cell_microcrack_inspector: 3, tcp_retransmission_monitor: 4, unsupported: 6, wrist_scaphoid_fracture_triage: 4
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20

### RQ4/K254 (test, n=300)

- **service_type**: academic_transcript_parser: 1, air_quality_pm25_analyzer: 1, aisle_congestion_monitor: 1, ambient_noise_level_meter: 1, ambient_weather_station_aggregator: 1, animal_detector: 1, anti_passback_enforcer: 1, ar_marker_bundle_adjuster: 1, arp_spoofing_detector: 1, audio_downsampling_resampler: 1, audio_event_classifier: 1, audio_flac_to_opus_compressor: 1, audio_guide_multilingual_synthesizer: 1, av1_video_transcoder: 1, badge_credential_reader: 1, bank_check_micr_parser: 1, bank_statement_table_parser: 1, bedside_lung_ultrasound_pneumothorax_triage: 1, bgp_route_leak_detector: 1, bicycle_counter: 1, bicycle_lane_blockage_detector: 1, bill_of_lading_parser: 1, billboard_text_ocr: 1, biometric_fingerprint_reader: 1, bone_radiograph_fracture_triage: 1, bottle_fill_level_inspector: 1, bridge_overheight_vehicle_detector: 1, bufferbloat_queue_analyzer: 1, bus_lane_encroachment_detector: 1, business_card_ocr: 1, camera_tamper_detector: 1, car_alarm_detector: 1, cart_abandonment_tracker: 1, carton_counter: 1, cell_counter: 1, chat_message_translator: 1, chest_xray_pneumonia_triage: 1, circuit_board_silkscreen_ocr: 1, co2_indoor_ventilation_monitor: 1, construction_activity_analyzer: 1, container_code_ocr: 1, container_stack_counter: 1, conveyor_belt_tear_inspector: 1, coronary_calcium_ct_triage: 1, cough_detector: 1, count: 1, coupon_kiosk_engagement_meter: 1, crane_hook_detector: 1, crosswalk_jaywalking_detector: 2, crowd_head_counter: 1, crowd_surge_detector: 1, cry_detector: 1, ct_brain_hemorrhage_triage: 1, customer_dwell_time_meter: 1, customs_declaration_parser: 1, cyclist_detector: 1, ddos_syn_flood_detector: 1, de_to_en_industrial_translator: 1, dense_depth_map_completer: 1, dental_caries_xray_triage: 1, detection: 2, dicom_medical_image_compressor: 1, dns_tunneling_detector: 1, docking_bay_dwell_analyzer: 1, door_forced_open_detector: 1, door_held_open_notifier: 1, drone_acoustic_classifier: 1, drone_detector: 2, drone_perimeter_alert: 1, ecg_arrhythmia_triage: 1, emergency_phrase_translator: 1, emergency_siren_detector: 2, en_to_de_industrial_translator: 2, en_to_es_speech_translator: 1, en_to_fr_document_translator: 1, en_to_ja_menu_translator: 2, en_to_zh_subtitle_generator: 1, endcap_promotional_gaze_tracker: 2, endoscopy_polyps_triage: 1, es_to_en_speech_translator: 1, escalator_stoppage_detector: 1, ev_charging_bay_hogging_detector: 1, eye_gaze_direction_tracker: 1, fabric_defect_inspector: 1, facial_access_verifier: 1, facial_blendshape_animator: 1, fence_climbing_detector: 1, fire_detector: 1, fitting_room_occupancy_sensor: 1, flood_water_level_gauge: 1, flow_volume_anomaly_detector: 2, food_package_seal_inspector: 2, footwear_try_on_counter: 1, forklift_detector: 1, fr_to_en_document_translator: 1, fundus_diabetic_retinopathy_triage: 1, gaussian_splat_renderer: 1, geotiff_raster_compressor: 1, glass_break_detector: 1, glass_vial_crack_inspector: 1, grab_and_go_basket_tracker: 1, gunshot_detector: 1, h264_bitrate_downscaler: 1, h265_video_transcoder: 1, hand_mesh_pose_tracker: 2, handwritten_form_ocr: 1, handwritten_survey_digitizer: 1, hazard_cone_detector: 1, hdr_to_sdr_tone_mapper: 1, heat_map_path_analyzer: 1, highway_ramp_metering_analyzer: 1, hov_lane_occupancy_verifier: 1, identity_card_extractor: 1, illegal_parking_meter: 1, industrial_bearing_monitor: 1, injection_molding_short_shot_inspector: 1, instrument_gauge_ocr: 1, insurance_claim_form_parser: 1, interface_flapping_detector: 1, intersection_turning_count_analyzer: 1, invoice_data_extractor: 1, ip_fragmentation_attack_detector: 1, iris_biometric_authenticator: 1, ja_to_en_menu_translator: 1, jpeg_to_webp_converter: 1, json_to_protobuf_serializer: 1, label_alignment_inspector: 1, language_identifier: 1, legal_contract_clause_tagger: 1, license_plate_barrier_opener: 1, license_plate_ocr: 1, live_dialogue_interpreter: 1, livestock_counter: 1, loitering_at_atm_detector: 1, loitering_detector: 1, loss_prevention_sweethearting_detector: 1, lossless_log_zstd_compressor: 1, luggage_counter: 1, mammogram_mass_triage: 1, medical_prescription_parser: 1, mesh_simplifier_lod: 1, meter_reading_ocr: 1, multicast_storm_suppressor: 1, multilingual_sign_translator: 2, noise_pollution_monitor: 1, ntp_clock_drift_monitor: 1, occlusion_culling_optimizer: 1, ocean_wave_height_buoy_analyzer: 1, ocr: 1, package_xray_contraband_screener: 1, packet_jitter_analyzer: 1, paint_scratch_inspector: 1, pallet_counter: 1, parking_spot_counter: 1, parquet_columnar_encoder: 1, passport_mrz_ocr: 1, pcb_solder_bridge_inspector: 1, pedestrian_crosswalk_occupancy_sensor: 2, pedestrian_detector: 1, people_counter: 1, perimeter_intrusion_detector: 1, photorealistic_light_estimator: 1, planogram_compliance_checker: 1, point_cloud_draco_compressor: 1, point_cloud_mesher: 1, pothole_road_surface_scanner: 1, ppe_detector: 1, prescription_label_ocr: 1, produce_ripeness_scanner: 1, product_unit_counter: 1, puddle_detector: 1, purchase_order_matcher: 1, queue_length_analyzer: 1, radiation_geiger_counter_monitor: 1, rail_crossing_blockage_detector: 1, rail_level_crossing_queue_monitor: 1, receipt_expense_categorizer: 1, receipt_text_ocr: 1, refrigeration_temperature_compliance_logger: 1, retinal_oct_macular_edema_triage: 2, rogue_dhcp_server_detector: 1, roundabout_gap_analyzer: 1, rubber_o_ring_flaw_inspector: 1, runway_incursion_detector: 1, school_zone_speed_monitor: 1, seat_occupancy_counter: 1, secure_server_rack_door_monitor: 1, self_checkout_item_mismatch_detector: 1, shadow_map_projector: 1, sheet_metal_burr_inspector: 1, shelf_out_of_stock_detector: 1, shelf_tag_ocr: 1, shipping_label_ocr: 1, shipping_manifest_digitizer: 1, shopper_gender_age_estimator: 1, shopping_basket_volume_estimator: 1, shopping_cart_detector: 1, skin_lesion_melanoma_triage: 1, slam_pose_tracker: 1, slip_and_fall_detector: 1, soil_moisture_irrigation_controller: 1, solar_cell_microcrack_inspector: 1, solar_panel_counter: 2, spatial_audio_binauralizer: 1, speaker_diarization: 1, speech_to_text: 1, speeding_vehicle_detector: 1, spill_detector: 1, spinal_fracture_xray_triage: 1, ssl_certificate_expiry_watcher: 1, stroke_mri_diffusion_triage: 1, structural_vibration_accelerometer: 1, surface_plane_detector: 1, tablet_pill_blister_inspector: 1, tailgating_access_interceptor: 1, tailgating_detector: 1, tax_form_w2_parser: 1, tcp_retransmission_monitor: 1, technical_terminology_normalizer: 1, texture_atlas_baker: 1, threaded_screw_inspector: 1, time_series_gorilla_compressor: 1, tire_dot_ocr: 1, tls_fingerprint_classifier: 1, toxic_gas_h2s_leak_detector: 1, traffic_congestion_analyzer: 2, traffic_incident_detector: 1, traffic_light_violation_detector: 1, tree_crown_counter: 1, turbine_blade_thermal_inspector: 1, ultrasound_dvt_triage: 1, unattended_baggage_detector: 1, under_vehicle_inspection_scanner: 1, unsupported: 30, utility_bill_parser: 1, uv_index_solar_radiometer: 1, vehicle_counter: 1, vehicle_detector: 1, video_keyframe_extractor: 1, vin_ocr: 1, virtual_object_occlusion_masker: 1, visitor_id_scanner: 1, voice_stress_analyzer: 1, volatile_organic_compound_voc_sensor: 1, wake_word_spotter: 1, water_leak_acoustic_detector: 1, water_turbidity_clarity_meter: 1, weapon_detector: 1, weld_seam_flaw_inspector: 1, wifi_channel_interference_analyzer: 1, wildfire_thermal_hotspot_detector: 1, work_zone_merge_compliance_monitor: 2, wrist_scaphoid_fracture_triage: 1, wrong_way_driver_detector: 1, zh_to_en_subtitle_generator: 1
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100

### RQ4/K254 (dev, n=60)

- **service_type**: aisle_congestion_monitor: 1, ambient_noise_level_meter: 1, animal_detector: 1, bedside_lung_ultrasound_pneumothorax_triage: 1, biometric_fingerprint_reader: 1, bufferbloat_queue_analyzer: 1, camera_tamper_detector: 1, carton_counter: 1, circuit_board_silkscreen_ocr: 1, co2_indoor_ventilation_monitor: 1, construction_activity_analyzer: 1, coronary_calcium_ct_triage: 1, crowd_head_counter: 1, ct_brain_hemorrhage_triage: 1, customs_declaration_parser: 1, dental_caries_xray_triage: 1, door_held_open_notifier: 1, drone_detector: 1, ecg_arrhythmia_triage: 1, emergency_phrase_translator: 1, footwear_try_on_counter: 1, heat_map_path_analyzer: 1, industrial_bearing_monitor: 1, insurance_claim_form_parser: 1, intersection_turning_count_analyzer: 1, json_to_protobuf_serializer: 1, license_plate_barrier_opener: 1, loitering_detector: 1, meter_reading_ocr: 1, noise_pollution_monitor: 1, ocean_wave_height_buoy_analyzer: 1, photorealistic_light_estimator: 1, planogram_compliance_checker: 1, purchase_order_matcher: 1, radiation_geiger_counter_monitor: 1, rubber_o_ring_flaw_inspector: 1, runway_incursion_detector: 1, shelf_tag_ocr: 1, shipping_manifest_digitizer: 1, shopper_gender_age_estimator: 1, slam_pose_tracker: 1, ssl_certificate_expiry_watcher: 1, structural_vibration_accelerometer: 1, traffic_incident_detector: 1, turbine_blade_thermal_inspector: 1, unattended_baggage_detector: 1, unsupported: 6, uv_index_solar_radiometer: 1, vehicle_detector: 1, video_keyframe_extractor: 1, visitor_id_scanner: 1, voice_stress_analyzer: 1, wake_word_spotter: 1, wifi_channel_interference_analyzer: 1, wrist_scaphoid_fracture_triage: 1
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20

### RQ4/K4 (test, n=300)

- **service_type**: count: 67, detection: 68, ocr: 67, tcp_retransmission_monitor: 68, unsupported: 30
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100

### RQ4/K4 (dev, n=60)

- **service_type**: count: 13, detection: 13, ocr: 14, tcp_retransmission_monitor: 14, unsupported: 6
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20

### RQ4/K64 (test, n=300)

- **service_type**: air_quality_pm25_analyzer: 5, ar_marker_bundle_adjuster: 4, audio_downsampling_resampler: 5, bgp_route_leak_detector: 4, bridge_overheight_vehicle_detector: 4, camera_tamper_detector: 4, car_alarm_detector: 5, chat_message_translator: 4, container_stack_counter: 4, coronary_calcium_ct_triage: 4, count: 4, crowd_surge_detector: 4, customs_declaration_parser: 4, dense_depth_map_completer: 4, detection: 4, drone_perimeter_alert: 4, emergency_siren_detector: 4, facial_blendshape_animator: 4, fence_climbing_detector: 4, fitting_room_occupancy_sensor: 4, fundus_diabetic_retinopathy_triage: 4, gaussian_splat_renderer: 4, geotiff_raster_compressor: 4, h264_bitrate_downscaler: 5, handwritten_form_ocr: 5, industrial_bearing_monitor: 4, insurance_claim_form_parser: 4, ip_fragmentation_attack_detector: 4, ja_to_en_menu_translator: 5, json_to_protobuf_serializer: 4, label_alignment_inspector: 4, loss_prevention_sweethearting_detector: 5, medical_prescription_parser: 5, ocr: 5, packet_jitter_analyzer: 5, parking_spot_counter: 4, pcb_solder_bridge_inspector: 4, pothole_road_surface_scanner: 4, prescription_label_ocr: 4, produce_ripeness_scanner: 4, product_unit_counter: 4, puddle_detector: 4, radiation_geiger_counter_monitor: 4, roundabout_gap_analyzer: 4, rubber_o_ring_flaw_inspector: 4, runway_incursion_detector: 4, secure_server_rack_door_monitor: 4, self_checkout_item_mismatch_detector: 4, shipping_label_ocr: 4, shipping_manifest_digitizer: 5, skin_lesion_melanoma_triage: 4, solar_cell_microcrack_inspector: 4, tcp_retransmission_monitor: 4, technical_terminology_normalizer: 5, unattended_baggage_detector: 4, unsupported: 30, uv_index_solar_radiometer: 4, visitor_id_scanner: 5, wake_word_spotter: 4, weapon_detector: 4, wildfire_thermal_hotspot_detector: 4, work_zone_merge_compliance_monitor: 4, wrist_scaphoid_fracture_triage: 5, wrong_way_driver_detector: 4, zh_to_en_subtitle_generator: 4
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100

### RQ4/K64 (dev, n=60)

- **service_type**: ar_marker_bundle_adjuster: 1, bgp_route_leak_detector: 1, bridge_overheight_vehicle_detector: 1, camera_tamper_detector: 1, car_alarm_detector: 1, container_stack_counter: 1, coronary_calcium_ct_triage: 1, count: 1, crowd_surge_detector: 1, customs_declaration_parser: 1, dense_depth_map_completer: 1, detection: 1, facial_blendshape_animator: 1, fence_climbing_detector: 1, fitting_room_occupancy_sensor: 1, gaussian_splat_renderer: 1, geotiff_raster_compressor: 1, h264_bitrate_downscaler: 1, handwritten_form_ocr: 1, industrial_bearing_monitor: 1, insurance_claim_form_parser: 1, ip_fragmentation_attack_detector: 1, ja_to_en_menu_translator: 1, json_to_protobuf_serializer: 1, label_alignment_inspector: 1, loss_prevention_sweethearting_detector: 1, medical_prescription_parser: 1, packet_jitter_analyzer: 1, parking_spot_counter: 1, pcb_solder_bridge_inspector: 1, pothole_road_surface_scanner: 1, prescription_label_ocr: 1, produce_ripeness_scanner: 1, product_unit_counter: 1, radiation_geiger_counter_monitor: 1, rubber_o_ring_flaw_inspector: 1, runway_incursion_detector: 1, secure_server_rack_door_monitor: 1, self_checkout_item_mismatch_detector: 1, shipping_label_ocr: 1, shipping_manifest_digitizer: 1, skin_lesion_melanoma_triage: 1, solar_cell_microcrack_inspector: 1, tcp_retransmission_monitor: 1, technical_terminology_normalizer: 1, unattended_baggage_detector: 1, unsupported: 6, uv_index_solar_radiometer: 1, visitor_id_scanner: 1, wake_word_spotter: 1, weapon_detector: 1, wildfire_thermal_hotspot_detector: 1, work_zone_merge_compliance_monitor: 1, wrist_scaphoid_fracture_triage: 1, wrong_way_driver_detector: 1
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20

### RQ4/churn25 (test, n=300)

- **service_type**: ambient_weather_station_aggregator: 4, ar_marker_bundle_adjuster: 4, audio_downsampling_resampler: 4, audio_event_classifier: 5, bgp_route_leak_detector: 5, bridge_overheight_vehicle_detector: 4, camera_tamper_detector: 4, chat_message_translator: 4, container_stack_counter: 5, conveyor_belt_tear_inspector: 4, coronary_calcium_ct_triage: 4, count: 4, crane_hook_detector: 5, crowd_surge_detector: 4, customs_declaration_parser: 4, dense_depth_map_completer: 5, drone_perimeter_alert: 4, facial_blendshape_animator: 4, fence_climbing_detector: 4, fitting_room_occupancy_sensor: 4, flood_water_level_gauge: 5, fundus_diabetic_retinopathy_triage: 4, gaussian_splat_renderer: 4, geotiff_raster_compressor: 4, glass_break_detector: 4, glass_vial_crack_inspector: 4, h264_bitrate_downscaler: 5, handwritten_form_ocr: 5, hazard_cone_detector: 5, insurance_claim_form_parser: 4, ip_fragmentation_attack_detector: 4, ja_to_en_menu_translator: 5, json_to_protobuf_serializer: 4, loss_prevention_sweethearting_detector: 4, medical_prescription_parser: 4, ocr: 5, packet_jitter_analyzer: 4, parking_spot_counter: 4, pedestrian_detector: 4, pothole_road_surface_scanner: 5, prescription_label_ocr: 4, produce_ripeness_scanner: 4, product_unit_counter: 4, refrigeration_temperature_compliance_logger: 4, roundabout_gap_analyzer: 5, runway_incursion_detector: 4, secure_server_rack_door_monitor: 4, self_checkout_item_mismatch_detector: 4, shipping_label_ocr: 4, shipping_manifest_digitizer: 5, skin_lesion_melanoma_triage: 4, speech_to_text: 4, tcp_retransmission_monitor: 4, technical_terminology_normalizer: 4, turbine_blade_thermal_inspector: 4, unsupported: 30, vehicle_detector: 4, visitor_id_scanner: 4, water_leak_acoustic_detector: 4, water_turbidity_clarity_meter: 4, weld_seam_flaw_inspector: 4, work_zone_merge_compliance_monitor: 4, wrist_scaphoid_fracture_triage: 4, wrong_way_driver_detector: 4, zh_to_en_subtitle_generator: 4
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100

### RQ4/churn25 (dev, n=60)

- **service_type**: ambient_weather_station_aggregator: 1, ar_marker_bundle_adjuster: 1, audio_event_classifier: 1, bgp_route_leak_detector: 1, bridge_overheight_vehicle_detector: 1, camera_tamper_detector: 1, chat_message_translator: 1, container_stack_counter: 1, crane_hook_detector: 1, dense_depth_map_completer: 1, drone_perimeter_alert: 1, facial_blendshape_animator: 1, fence_climbing_detector: 1, fitting_room_occupancy_sensor: 1, flood_water_level_gauge: 1, fundus_diabetic_retinopathy_triage: 1, gaussian_splat_renderer: 1, glass_break_detector: 1, glass_vial_crack_inspector: 1, handwritten_form_ocr: 1, hazard_cone_detector: 1, insurance_claim_form_parser: 1, ip_fragmentation_attack_detector: 1, ja_to_en_menu_translator: 1, loss_prevention_sweethearting_detector: 1, medical_prescription_parser: 1, ocr: 1, parking_spot_counter: 1, pedestrian_detector: 1, pothole_road_surface_scanner: 1, prescription_label_ocr: 1, produce_ripeness_scanner: 1, product_unit_counter: 1, refrigeration_temperature_compliance_logger: 1, roundabout_gap_analyzer: 1, runway_incursion_detector: 1, secure_server_rack_door_monitor: 1, self_checkout_item_mismatch_detector: 1, shipping_label_ocr: 1, shipping_manifest_digitizer: 1, skin_lesion_melanoma_triage: 1, speech_to_text: 1, tcp_retransmission_monitor: 1, technical_terminology_normalizer: 1, turbine_blade_thermal_inspector: 1, unsupported: 6, vehicle_detector: 1, visitor_id_scanner: 1, water_leak_acoustic_detector: 1, water_turbidity_clarity_meter: 1, weld_seam_flaw_inspector: 1, work_zone_merge_compliance_monitor: 1, wrist_scaphoid_fracture_triage: 1, wrong_way_driver_detector: 1, zh_to_en_subtitle_generator: 1
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20

### RQ4/churn50 (test, n=300)

- **service_type**: academic_transcript_parser: 4, ar_marker_bundle_adjuster: 4, audio_downsampling_resampler: 5, bank_statement_table_parser: 4, bedside_lung_ultrasound_pneumothorax_triage: 4, bridge_overheight_vehicle_detector: 4, bufferbloat_queue_analyzer: 4, business_card_ocr: 4, camera_tamper_detector: 4, car_alarm_detector: 4, chest_xray_pneumonia_triage: 4, co2_indoor_ventilation_monitor: 5, container_stack_counter: 4, count: 4, crowd_surge_detector: 5, dense_depth_map_completer: 5, dental_caries_xray_triage: 5, detection: 4, door_forced_open_detector: 4, emergency_siren_detector: 4, en_to_es_speech_translator: 5, en_to_fr_document_translator: 4, es_to_en_speech_translator: 5, facial_access_verifier: 4, facial_blendshape_animator: 5, fitting_room_occupancy_sensor: 5, flow_volume_anomaly_detector: 4, food_package_seal_inspector: 5, gaussian_splat_renderer: 4, geotiff_raster_compressor: 4, glass_vial_crack_inspector: 4, h264_bitrate_downscaler: 4, industrial_bearing_monitor: 4, injection_molding_short_shot_inspector: 4, iris_biometric_authenticator: 4, json_to_protobuf_serializer: 5, live_dialogue_interpreter: 4, loss_prevention_sweethearting_detector: 4, meter_reading_ocr: 4, noise_pollution_monitor: 4, parking_spot_counter: 4, passport_mrz_ocr: 4, pothole_road_surface_scanner: 4, produce_ripeness_scanner: 5, product_unit_counter: 4, puddle_detector: 4, roundabout_gap_analyzer: 4, runway_incursion_detector: 4, self_checkout_item_mismatch_detector: 4, tax_form_w2_parser: 4, tls_fingerprint_classifier: 4, turbine_blade_thermal_inspector: 4, ultrasound_dvt_triage: 4, unattended_baggage_detector: 4, under_vehicle_inspection_scanner: 5, unsupported: 30, utility_bill_parser: 4, vin_ocr: 4, volatile_organic_compound_voc_sensor: 4, wake_word_spotter: 4, water_turbidity_clarity_meter: 4, weapon_detector: 4, wifi_channel_interference_analyzer: 4, work_zone_merge_compliance_monitor: 4, wrong_way_driver_detector: 5
- **locality**: remote_allowed: 100, site_only: 100, unspecified: 100
- **quality_floor**: high: 100, standard: 100, unspecified: 100
- **urgency**: normal: 100, unspecified: 100, urgent: 100

### RQ4/churn50 (dev, n=60)

- **service_type**: academic_transcript_parser: 1, ar_marker_bundle_adjuster: 1, audio_downsampling_resampler: 1, bedside_lung_ultrasound_pneumothorax_triage: 1, bridge_overheight_vehicle_detector: 1, bufferbloat_queue_analyzer: 1, business_card_ocr: 1, camera_tamper_detector: 1, car_alarm_detector: 1, chest_xray_pneumonia_triage: 1, co2_indoor_ventilation_monitor: 1, container_stack_counter: 1, count: 1, crowd_surge_detector: 1, dense_depth_map_completer: 1, dental_caries_xray_triage: 1, detection: 1, door_forced_open_detector: 1, en_to_es_speech_translator: 1, en_to_fr_document_translator: 1, fitting_room_occupancy_sensor: 1, flow_volume_anomaly_detector: 1, food_package_seal_inspector: 1, gaussian_splat_renderer: 1, geotiff_raster_compressor: 1, glass_vial_crack_inspector: 1, industrial_bearing_monitor: 1, iris_biometric_authenticator: 1, json_to_protobuf_serializer: 1, live_dialogue_interpreter: 1, loss_prevention_sweethearting_detector: 1, meter_reading_ocr: 1, noise_pollution_monitor: 1, parking_spot_counter: 1, passport_mrz_ocr: 1, pothole_road_surface_scanner: 1, produce_ripeness_scanner: 1, product_unit_counter: 1, roundabout_gap_analyzer: 1, runway_incursion_detector: 1, self_checkout_item_mismatch_detector: 1, tax_form_w2_parser: 1, tls_fingerprint_classifier: 1, turbine_blade_thermal_inspector: 1, ultrasound_dvt_triage: 1, unattended_baggage_detector: 1, under_vehicle_inspection_scanner: 1, unsupported: 6, utility_bill_parser: 1, vin_ocr: 1, wake_word_spotter: 1, water_turbidity_clarity_meter: 1, weapon_detector: 1, wifi_channel_interference_analyzer: 1, work_zone_merge_compliance_monitor: 1
- **locality**: remote_allowed: 20, site_only: 20, unspecified: 20
- **quality_floor**: high: 20, standard: 20, unspecified: 20
- **urgency**: normal: 20, unspecified: 20, urgent: 20
