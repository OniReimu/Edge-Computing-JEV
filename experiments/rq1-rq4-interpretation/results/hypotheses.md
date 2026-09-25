# Confirmatory Hypotheses Evaluation (H1–H5)

Evaluation against pre-registered analysis plan (`analysis-plan.md`, frozen 2026-09-24).
Decision rule: resolved = 95% CI excludes null value AND Holm-adjusted p < 0.05.

## Summary of Confirmatory Status

| Hypothesis | Target RQ | Family | Contrasts Tested | Resolved | Notes |
|---|---|---|---|---|---|
| **H1(a)** | RQ1a | Latency difference | 20 | 20 | Gated out: 0 levels |
| **H1(b)** | RQ1a | Ratio-of-ratios | 4 | 3 | not resolved: G_SemIf-Qwen3.5-4B(16K) / G_Qwen3.5-4B-JSON(16K) |
| **H2** | RQ1b | Per-request ratio-of-ratios | 4 | 4 | all resolved |
| **H3 (Omnibus)** | RQ2 | Cochran's Q on unsafe | 8 | 8 | all resolved |
| **H3 (Paired)** | RQ2 | Unsafe difference vs Jev | 40 | 7 | not resolved: DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ clean; GLM-5.3-Flash - Jev-1.13.0 unsafe @ clean; Qwen3.8-Flash - Jev-1.13.0 unsafe @ clean; SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ clean; DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ codeswitch; GLM-5.3-Flash - Jev-1.13.0 unsafe @ codeswitch; Qwen3.8-Flash - Jev-1.13.0 unsafe @ codeswitch; SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ codeswitch; DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ colloquial; GLM-5.3-Flash - Jev-1.13.0 unsafe @ colloquial; Qwen3.8-Flash - Jev-1.13.0 unsafe @ colloquial; SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ colloquial; DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ defaultbait; GLM-5.3-Flash - Jev-1.13.0 unsafe @ defaultbait; Qwen3.8-Flash - Jev-1.13.0 unsafe @ defaultbait; SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ defaultbait; DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ keyvalue; GLM-5.3-Flash - Jev-1.13.0 unsafe @ keyvalue; Qwen3.8-Flash - Jev-1.13.0 unsafe @ keyvalue; SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ keyvalue; Laya - Jev-1.13.0 unsafe @ keyvalue; DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ negation; GLM-5.3-Flash - Jev-1.13.0 unsafe @ negation; Qwen3.8-Flash - Jev-1.13.0 unsafe @ negation; SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ negation; DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ noise; GLM-5.3-Flash - Jev-1.13.0 unsafe @ noise; Qwen3.8-Flash - Jev-1.13.0 unsafe @ noise; SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ noise; DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ revised; GLM-5.3-Flash - Jev-1.13.0 unsafe @ revised; Qwen3.8-Flash - Jev-1.13.0 unsafe @ revised; SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ revised |
| **H4 (Tokens)** | RQ3 | Output tokens diff | 3 | 3 | all resolved |
| **H4 (Latency)** | RQ3 | Latency ratio-of-ratios | 4 | 4 | all resolved |
| **H5** | RQ4b | Catalog gap churn25/50 | 16 | 16 | all resolved |

## Gating Status (H1a Valid Rate >= 90%)

- No levels were gated out: all evaluated models achieved >= 90% valid rate.

## Flagged cells

Per analysis plan ("Cells with valid rate < 50% are still tested (no screening), and flagged"): 

- **SemIf-Qwen3.5-4B** (RQ4/K64): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "Question 'r1__service_type' has 65 options; SemIf supports 2-16 options"
- **SemIf-Qwen3.5-4B** (RQ4/K128): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "Question 'r1__service_type' has 129 options; SemIf supports 2-16 options"
- **SemIf-Qwen3.5-4B** (RQ4/K254): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "Question 'r1__service_type' has 255 options; SemIf supports 2-16 options"
- **Laya** (RQ4/K254): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "question 'r1__service_type' options exceed head_max_len=256"
- **SemIf-Qwen3.5-4B** (RQ4/churn25): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "Question 'r1__service_type' has 65 options; SemIf supports 2-16 options"
- **SemIf-Qwen3.5-4B** (RQ4/churn50): valid rate = 0.0%, dominant error_type = HTTP_400, example raw_response: "Question 'r1__service_type' has 65 options; SemIf supports 2-16 options"

### H1(a): Paired Latency Difference (LLM - Jev > 0)

| Contrast | Level | Estimate | 95% CI | Raw p | Holm p | Verdict | Notes |
|---|---|---|---|---|---|---|---|
| DeepSeek-V4.1-Flash - Jev-1.13.0 @ base | base | 0.1091 | [0.1015, 0.1172] | 1.2636e-46 | 3.7909e-46 | **resolved** | n_paired=300 |
| DeepSeek-V4.1-Flash - Jev-1.13.0 @ pad_512 | pad_512 | 0.2166 | [0.2037, 0.2314] | 9.7442e-49 | 5.8465e-48 | **resolved** | n_paired=300 |
| DeepSeek-V4.1-Flash - Jev-1.13.0 @ pad_2048 | pad_2048 | 0.2694 | [0.2565, 0.2827] | 9.6183e-50 | 6.7328e-49 | **resolved** | n_paired=300 |
| DeepSeek-V4.1-Flash - Jev-1.13.0 @ pad_8192 | pad_8192 | 0.1647 | [0.1508, 0.1829] | 6.8415e-42 | 6.8415e-42 | **resolved** | n_paired=300 |
| DeepSeek-V4.1-Flash - Jev-1.13.0 @ pad_16384 | pad_16384 | 0.2179 | [0.2043, 0.2363] | 5.8199e-46 | 1.1640e-45 | **resolved** | n_paired=300 |
| GLM-5.3-Flash - Jev-1.13.0 @ base | base | 0.3700 | [0.3468, 0.3956] | 5.4109e-50 | 4.8698e-49 | **resolved** | n_paired=300 |
| GLM-5.3-Flash - Jev-1.13.0 @ pad_512 | pad_512 | 0.4475 | [0.4250, 0.4704] | 6.4608e-51 | 1.2167e-49 | **resolved** | n_paired=300 |
| GLM-5.3-Flash - Jev-1.13.0 @ pad_2048 | pad_2048 | 0.4002 | [0.3698, 0.4275] | 6.0836e-51 | 1.2167e-49 | **resolved** | n_paired=300 |
| GLM-5.3-Flash - Jev-1.13.0 @ pad_8192 | pad_8192 | 0.7509 | [0.7224, 0.8109] | 7.8112e-50 | 6.2490e-49 | **resolved** | n_paired=300 |
| GLM-5.3-Flash - Jev-1.13.0 @ pad_16384 | pad_16384 | 1.1564 | [1.0720, 1.2181] | 1.6734e-47 | 6.6937e-47 | **resolved** | n_paired=300 |
| Qwen3.8-Flash - Jev-1.13.0 @ base | base | 1.4723 | [1.3787, 1.6162] | 6.0836e-51 | 1.2167e-49 | **resolved** | n_paired=300 |
| Qwen3.8-Flash - Jev-1.13.0 @ pad_512 | pad_512 | 1.3580 | [1.2940, 1.4586] | 6.0836e-51 | 1.2167e-49 | **resolved** | n_paired=300 |
| Qwen3.8-Flash - Jev-1.13.0 @ pad_2048 | pad_2048 | 1.3143 | [1.2736, 1.3485] | 6.0836e-51 | 1.2167e-49 | **resolved** | n_paired=300 |
| Qwen3.8-Flash - Jev-1.13.0 @ pad_8192 | pad_8192 | 1.9937 | [1.9461, 2.0656] | 6.0836e-51 | 1.2167e-49 | **resolved** | n_paired=300 |
| Qwen3.8-Flash - Jev-1.13.0 @ pad_16384 | pad_16384 | 2.4974 | [2.4161, 2.5531] | 9.8402e-49 | 5.8465e-48 | **resolved** | n_paired=300 |
| Qwen3.5-4B-JSON - SemIf-Qwen3.5-4B @ base | base | 0.6480 | [0.6350, 0.6495] | 6.0836e-51 | 1.2167e-49 | **resolved** | n_paired=300 |
| Qwen3.5-4B-JSON - SemIf-Qwen3.5-4B @ pad_512 | pad_512 | 0.6370 | [0.6330, 0.6460] | 6.0836e-51 | 1.2167e-49 | **resolved** | n_paired=300 |
| Qwen3.5-4B-JSON - SemIf-Qwen3.5-4B @ pad_2048 | pad_2048 | 0.6450 | [0.6435, 0.6460] | 6.0836e-51 | 1.2167e-49 | **resolved** | n_paired=300 |
| Qwen3.5-4B-JSON - SemIf-Qwen3.5-4B @ pad_8192 | pad_8192 | 0.5340 | [0.5320, 0.5369] | 6.0836e-51 | 1.2167e-49 | **resolved** | n_paired=300 |
| Qwen3.5-4B-JSON - SemIf-Qwen3.5-4B @ pad_16384 | pad_16384 | 0.3930 | [0.3910, 0.3950] | 6.0836e-51 | 1.2167e-49 | **resolved** | n_paired=300 |

### H1(b): Latency Growth Ratio-of-Ratios (< 1.0)

| Contrast | Level | Estimate | 95% CI | Raw p | Holm p | Verdict | Notes |
|---|---|---|---|---|---|---|---|
| G_Jev-1.13.0(16K) / G_DeepSeek-V4.1-Flash(16K) | pad_16384 vs base | 0.9045 | [0.8648, 0.9403] | < 1e-4 | 3.9996e-04 | **resolved** | n_cases=300 |
| G_Jev-1.13.0(16K) / G_GLM-5.3-Flash(16K) | pad_16384 vs base | 0.6220 | [0.5853, 0.6635] | < 1e-4 | 3.9996e-04 | **resolved** | n_cases=300 |
| G_Jev-1.13.0(16K) / G_Qwen3.8-Flash(16K) | pad_16384 vs base | 0.9286 | [0.8663, 0.9864] | 1.8400e-02 | 1.8400e-02 | **resolved** | n_cases=300 |
| G_SemIf-Qwen3.5-4B(16K) / G_Qwen3.5-4B-JSON(16K) | pad_16384 vs base | 4.6753 | [4.6655, 4.7013] | < 1e-4 | 3.9996e-04 | **not resolved** | n_cases=300 |

### H2: Per-Request Latency Ratio-of-Ratios (k=8 vs k=1, < 1.0)

| Contrast | Level | Estimate | 95% CI | Raw p | Holm p | Verdict | Notes |
|---|---|---|---|---|---|---|---|
| R_Jev-1.13.0(8) / R_DeepSeek-V4.1-Flash(8) | k8 vs k1 | 0.4942 | [0.4679, 0.5195] | < 1e-4 | 3.9996e-04 | **resolved** | n_cases=300 |
| R_Jev-1.13.0(8) / R_GLM-5.3-Flash(8) | k8 vs k1 | 0.3989 | [0.3791, 0.4271] | < 1e-4 | 3.9996e-04 | **resolved** | n_cases=300 |
| R_Jev-1.13.0(8) / R_Qwen3.8-Flash(8) | k8 vs k1 | 0.3673 | [0.3496, 0.3874] | < 1e-4 | 3.9996e-04 | **resolved** | n_cases=300 |
| R_SemIf-Qwen3.5-4B(8) / R_Qwen3.5-4B-JSON(8) | k8 vs k1 | 0.5281 | [0.5149, 0.5746] | < 1e-4 | 3.9996e-04 | **resolved** | n_cases=300 |

### H3: Omnibus Cochran's Q on Unsafe Locality across The Six

| Contrast | Level | Estimate | 95% CI | Raw p | Holm p | Verdict | Notes |
|---|---|---|---|---|---|---|---|
| Cochran's Q on unsafe across six @ clean | clean | 188.3000 | [188.3000, 188.3000] | 9.0192e-39 | 7.2154e-38 | **resolved** | df=5, n=300 |
| Cochran's Q on unsafe across six @ codeswitch | codeswitch | 171.9231 | [171.9231, 171.9231] | 2.8363e-35 | 1.7068e-34 | **resolved** | df=5, n=300 |
| Cochran's Q on unsafe across six @ colloquial | colloquial | 98.0000 | [98.0000, 98.0000] | 1.3946e-19 | 4.1838e-19 | **resolved** | df=5, n=300 |
| Cochran's Q on unsafe across six @ defaultbait | defaultbait | 82.6829 | [82.6829, 82.6829] | 2.3027e-16 | 4.6054e-16 | **resolved** | df=5, n=300 |
| Cochran's Q on unsafe across six @ keyvalue | keyvalue | 50.0000 | [50.0000, 50.0000] | 1.3858e-09 | 1.3858e-09 | **resolved** | df=5, n=300 |
| Cochran's Q on unsafe across six @ negation | negation | 120.3125 | [120.3125, 120.3125] | 2.6949e-24 | 1.0780e-23 | **resolved** | df=5, n=300 |
| Cochran's Q on unsafe across six @ noise | noise | 171.0488 | [171.0488, 171.0488] | 4.3584e-35 | 2.1792e-34 | **resolved** | df=5, n=300 |
| Cochran's Q on unsafe across six @ revised | revised | 172.2308 | [172.2308, 172.2308] | 2.4383e-35 | 1.7068e-34 | **resolved** | df=5, n=300 |

### H3: Paired Unsafe Differences vs Jev-1.13.0

| Contrast | Level | Estimate | 95% CI | Raw p | Holm p | Verdict | Notes |
|---|---|---|---|---|---|---|---|
| DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ clean | clean | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| GLM-5.3-Flash - Jev-1.13.0 unsafe @ clean | clean | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Qwen3.8-Flash - Jev-1.13.0 unsafe @ clean | clean | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ clean | clean | 0.0033 | [0.0000, 0.0100] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Laya - Jev-1.13.0 unsafe @ clean | clean | 0.1300 | [0.0933, 0.1700] | 3.6380e-12 | 1.4552e-10 | **resolved** | n_cases=300 |
| DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ codeswitch | codeswitch | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| GLM-5.3-Flash - Jev-1.13.0 unsafe @ codeswitch | codeswitch | 0.0033 | [0.0000, 0.0100] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Qwen3.8-Flash - Jev-1.13.0 unsafe @ codeswitch | codeswitch | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ codeswitch | codeswitch | 0.0033 | [0.0000, 0.0100] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Laya - Jev-1.13.0 unsafe @ codeswitch | codeswitch | 0.1233 | [0.0867, 0.1600] | 1.4552e-11 | 5.5297e-10 | **resolved** | n_cases=300 |
| DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ colloquial | colloquial | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| GLM-5.3-Flash - Jev-1.13.0 unsafe @ colloquial | colloquial | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Qwen3.8-Flash - Jev-1.13.0 unsafe @ colloquial | colloquial | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ colloquial | colloquial | 0.0067 | [0.0000, 0.0167] | 5.0000e-01 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Laya - Jev-1.13.0 unsafe @ colloquial | colloquial | 0.0733 | [0.0467, 0.1033] | 4.7684e-07 | 1.6689e-05 | **resolved** | n_cases=300 |
| DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ defaultbait | defaultbait | -0.0267 | [-0.0500, -0.0067] | 3.8574e-02 | 1.0000e+00 | **not resolved** | n_cases=300 |
| GLM-5.3-Flash - Jev-1.13.0 unsafe @ defaultbait | defaultbait | -0.0267 | [-0.0500, -0.0067] | 3.8574e-02 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Qwen3.8-Flash - Jev-1.13.0 unsafe @ defaultbait | defaultbait | 0.0067 | [-0.0167, 0.0300] | 7.9053e-01 | 1.0000e+00 | **not resolved** | n_cases=300 |
| SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ defaultbait | defaultbait | -0.0233 | [-0.0467, 0.0000] | 9.2285e-02 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Laya - Jev-1.13.0 unsafe @ defaultbait | defaultbait | 0.0900 | [0.0500, 0.1333] | 4.1934e-05 | 1.4258e-03 | **resolved** | n_cases=300 |
| DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ keyvalue | keyvalue | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| GLM-5.3-Flash - Jev-1.13.0 unsafe @ keyvalue | keyvalue | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Qwen3.8-Flash - Jev-1.13.0 unsafe @ keyvalue | keyvalue | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ keyvalue | keyvalue | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Laya - Jev-1.13.0 unsafe @ keyvalue | keyvalue | 0.0333 | [0.0133, 0.0567] | 1.9531e-03 | 6.4453e-02 | **not resolved** | n_cases=300 |
| DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ negation | negation | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| GLM-5.3-Flash - Jev-1.13.0 unsafe @ negation | negation | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Qwen3.8-Flash - Jev-1.13.0 unsafe @ negation | negation | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ negation | negation | 0.0033 | [0.0000, 0.0100] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Laya - Jev-1.13.0 unsafe @ negation | negation | 0.0833 | [0.0533, 0.1167] | 5.9605e-08 | 2.1458e-06 | **resolved** | n_cases=300 |
| DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ noise | noise | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| GLM-5.3-Flash - Jev-1.13.0 unsafe @ noise | noise | 0.0067 | [0.0000, 0.0167] | 5.0000e-01 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Qwen3.8-Flash - Jev-1.13.0 unsafe @ noise | noise | 0.0033 | [0.0000, 0.0100] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ noise | noise | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Laya - Jev-1.13.0 unsafe @ noise | noise | 0.1267 | [0.0900, 0.1633] | 7.2760e-12 | 2.8376e-10 | **resolved** | n_cases=300 |
| DeepSeek-V4.1-Flash - Jev-1.13.0 unsafe @ revised | revised | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| GLM-5.3-Flash - Jev-1.13.0 unsafe @ revised | revised | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Qwen3.8-Flash - Jev-1.13.0 unsafe @ revised | revised | 0.0000 | [0.0000, 0.0000] | 1.0000e+00 | 1.0000e+00 | **not resolved** | n_cases=300 |
| SemIf-Qwen3.5-4B - Jev-1.13.0 unsafe @ revised | revised | 0.0067 | [0.0000, 0.0167] | 5.0000e-01 | 1.0000e+00 | **not resolved** | n_cases=300 |
| Laya - Jev-1.13.0 unsafe @ revised | revised | 0.1233 | [0.0867, 0.1633] | 1.4552e-11 | 5.5297e-10 | **resolved** | n_cases=300 |

### H4: Output Tokens Growth (F=8 minus F=4 > 0)

| Contrast | Level | Estimate | 95% CI | Raw p | Holm p | Verdict | Notes |
|---|---|---|---|---|---|---|---|
| DeepSeek-V4.1-Flash output tokens F8 - F4 | F8 vs F4 pooled over D | 28.0000 | [27.0000, 28.0000] | < 1e-4 | 2.9997e-04 | **resolved** | n_pairs=900 |
| GLM-5.3-Flash output tokens F8 - F4 | F8 vs F4 pooled over D | 36.0000 | [35.0000, 37.0000] | < 1e-4 | 2.9997e-04 | **resolved** | n_pairs=884 |
| Qwen3.8-Flash output tokens F8 - F4 | F8 vs F4 pooled over D | 43.0000 | [42.0000, 44.5000] | < 1e-4 | 2.9997e-04 | **resolved** | n_pairs=886 |

### H4: Latency Growth Ratio-of-Ratios Pooled over D (< 1.0)

| Contrast | Level | Estimate | 95% CI | Raw p | Holm p | Verdict | Notes |
|---|---|---|---|---|---|---|---|
| G_Jev-1.13.0(F8/F4) / G_DeepSeek-V4.1-Flash(F8/F4) | F8 vs F4 pooled over D | 0.8283 | [0.8071, 0.8445] | < 1e-4 | 3.9996e-04 | **resolved** | n_pairs=900 (case-paired within D: 300 low, 300 med, 300 high) |
| G_Jev-1.13.0(F8/F4) / G_GLM-5.3-Flash(F8/F4) | F8 vs F4 pooled over D | 0.6376 | [0.6197, 0.6518] | < 1e-4 | 3.9996e-04 | **resolved** | n_pairs=900 (case-paired within D: 300 low, 300 med, 300 high) |
| G_Jev-1.13.0(F8/F4) / G_Qwen3.8-Flash(F8/F4) | F8 vs F4 pooled over D | 0.6504 | [0.6335, 0.6700] | < 1e-4 | 3.9996e-04 | **resolved** | n_pairs=900 (case-paired within D: 300 low, 300 med, 300 high) |
| G_SemIf-Qwen3.5-4B(F8/F4) / G_Qwen3.5-4B-JSON(F8/F4) | F8 vs F4 pooled over D | 0.5608 | [0.5594, 0.5623] | < 1e-4 | 3.9996e-04 | **resolved** | n_pairs=900 (case-paired within D: 300 low, 300 med, 300 high) |

### H5: Seen - Unseen Top-1 Accuracy Gap (< 10 pp)

| Contrast | Level | Estimate | 95% CI | Raw p | Holm p | Verdict | Notes |
|---|---|---|---|---|---|---|---|
| Jev-1.13.0 seen - unseen gap @ churn25 | churn25 | 0.0000 | [0.0000, 0.0000] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=0.0000 |
| DeepSeek-V4.1-Flash seen - unseen gap @ churn25 | churn25 | 0.0000 | [0.0000, 0.0000] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=0.0000 |
| GLM-5.3-Flash seen - unseen gap @ churn25 | churn25 | 0.0000 | [0.0000, 0.0000] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=0.0000 |
| Qwen3.8-Flash seen - unseen gap @ churn25 | churn25 | 0.0000 | [0.0000, 0.0000] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=0.0000 |
| SemIf-Qwen3.5-4B seen - unseen gap @ churn25 | churn25 | 0.0000 | [0.0000, 0.0000] | < 1e-4 | 1.5998e-03 | **resolved (flagged: valid <50%)** | upper_ci95=0.0000 |
| Laya seen - unseen gap @ churn25 | churn25 | -0.0533 | [-0.1934, 0.0829] | 2.6800e-02 | 2.6800e-02 | **resolved** | upper_ci95=0.0829 |
| Qwen3.5-4B-JSON seen - unseen gap @ churn25 | churn25 | -0.0198 | [-0.0410, -0.0048] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=-0.0048 |
| MiniLM-Reranker seen - unseen gap @ churn25 | churn25 | -0.0501 | [-0.1173, 0.0220] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=0.0220 |
| Jev-1.13.0 seen - unseen gap @ churn50 | churn50 | 0.0000 | [0.0000, 0.0000] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=0.0000 |
| DeepSeek-V4.1-Flash seen - unseen gap @ churn50 | churn50 | 0.0000 | [0.0000, 0.0000] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=0.0000 |
| GLM-5.3-Flash seen - unseen gap @ churn50 | churn50 | 0.0000 | [0.0000, 0.0000] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=0.0000 |
| Qwen3.8-Flash seen - unseen gap @ churn50 | churn50 | 0.0000 | [0.0000, 0.0000] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=0.0000 |
| SemIf-Qwen3.5-4B seen - unseen gap @ churn50 | churn50 | 0.0000 | [0.0000, 0.0000] | < 1e-4 | 1.5998e-03 | **resolved (flagged: valid <50%)** | upper_ci95=0.0000 |
| Laya seen - unseen gap @ churn50 | churn50 | -0.0834 | [-0.1977, 0.0312] | 8.0000e-04 | 1.6000e-03 | **resolved** | upper_ci95=0.0312 |
| Qwen3.5-4B-JSON seen - unseen gap @ churn50 | churn50 | -0.0145 | [-0.0526, 0.0202] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=0.0202 |
| MiniLM-Reranker seen - unseen gap @ churn50 | churn50 | -0.1020 | [-0.1795, -0.0276] | < 1e-4 | 1.5998e-03 | **resolved** | upper_ci95=-0.0276 |

## H5 Classifier References (Descriptive)

Descriptive comparison against supervised classifier references (DistilBERT):
- **Frozen classifier floor**: Head trained on C_64 v0; unseen accuracy is 0.0% by construction (floor).
- **Retrained classifier**: Head retrained with new churn services added to the label space. Adaptation cost shows added labelled examples and training wall time.

| Churn Level | Classifier | Seen Top-1 (95% CI) | Unseen Top-1 (95% CI) | Gap (95% CI) | Added Labelled Examples | Training Wall Time (s) |
|---|---|---|---|---|---|---|
| churn25 | DistilBERT-Clf-Frozen | 0.6535 [0.5859, 0.7171] | 0.0000 [0.0000, 0.0000] | 0.6535 [0.5859, 0.7171] | 0 | — |
| churn25 | DistilBERT-Clf-Retrained | 0.7079 [0.6442, 0.7692] | 0.1471 [0.0678, 0.2353] | 0.5609 [0.4514, 0.6626] | 76 | 12.82 |
| churn50 | DistilBERT-Clf-Frozen | 0.5221 [0.4388, 0.6074] | 0.0000 [0.0000, 0.0000] | 0.5221 [0.4388, 0.6074] | 0 | — |
| churn50 | DistilBERT-Clf-Retrained | 0.4412 [0.3588, 0.5238] | 0.1418 [0.0851, 0.2029] | 0.2994 [0.1977, 0.4021] | 92 | 10.02 |
