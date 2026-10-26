# Retrieval evaluation (M4)

BM25 over SWC Title/Description/Remediation text; query = the contract's code. Top-3 entries, 31 vulnerable contracts. No API calls.

| knowledge base | entries | labeled SWC in top-k | labeled class in top-k |
|---|---|---|---|
| all SWC entries (first design) | 37 | 9/31 | 14/31 |
| taxonomy entries only (used) | 17 | 15/31 | 20/31 |

The restriction to taxonomy entries was decided after measuring the first design once, and not tuned further. Both rows use the same 31 contracts, so the second number is optimistic.

## Per contract (knowledge base used)

| id | labeled SWC | retrieved | exact | class |
|---|---|---|---|---|
| c02 | SWC-100 | SWC-112, SWC-105, SWC-114 | - | yes |
| c04 | SWC-101 |  | - | - |
| c05 | SWC-120 | SWC-114, SWC-112, SWC-120 | yes | yes |
| c06 | SWC-105 | SWC-112, SWC-115, SWC-114 | - | yes |
| c08 | SWC-104 | SWC-112, SWC-128, SWC-104 | yes | yes |
| c09 | SWC-113 | SWC-118, SWC-128, SWC-105 | - | yes |
| c10 | SWC-115 | SWC-115, SWC-128, SWC-112 | yes | yes |
| c11 | SWC-128 | SWC-115, SWC-112, SWC-128 | yes | yes |
| c14 | SWC-117 | SWC-117, SWC-114, SWC-128 | yes | yes |
| c17 | SWC-107 | SWC-112, SWC-114, SWC-115 | - | - |
| c18 | SWC-118 | SWC-105, SWC-112, SWC-118 | yes | yes |
| c21 | SWC-107 | SWC-112, SWC-115, SWC-128 | - | - |
| c24 | SWC-124 | SWC-118, SWC-112, SWC-105 | - | yes |
| c25 | SWC-120 | SWC-114, SWC-105, SWC-120 | yes | yes |
| c26 | SWC-118 | SWC-112, SWC-105, SWC-115 | - | yes |
| c27 | SWC-107 | SWC-105, SWC-113, SWC-128 | - | - |
| c29 | SWC-114, SWC-116, SWC-120 | SWC-116, SWC-112, SWC-128 | yes | yes |
| c31 | SWC-112 | SWC-112, SWC-124, SWC-118 | yes | yes |
| c32 | SWC-106 | SWC-115, SWC-106, SWC-112 | yes | yes |
| c33 | SWC-101 | SWC-112 | - | - |
| c35 | SWC-104 | SWC-112, SWC-128, SWC-115 | - | - |
| c36 | SWC-116 | SWC-116, SWC-120, SWC-107 | yes | yes |
| c37 | SWC-101 | SWC-116, SWC-114, SWC-128 | - | - |
| c38 | SWC-101 | SWC-112 | - | - |
| c39 | SWC-114 | SWC-105, SWC-114, SWC-115 | yes | yes |
| c41 | SWC-128 | SWC-115, SWC-114, SWC-112 | - | - |
| c42 | SWC-101 | SWC-112 | - | - |
| c44 | SWC-120 | SWC-112, SWC-114, SWC-120 | yes | yes |
| c46 | SWC-109, SWC-120 | SWC-112, SWC-114, SWC-120 | yes | yes |
| c47 | SWC-114 | SWC-114, SWC-112, SWC-115 | yes | yes |
| c49 | SWC-116 | SWC-128, SWC-113, SWC-112 | - | - |
