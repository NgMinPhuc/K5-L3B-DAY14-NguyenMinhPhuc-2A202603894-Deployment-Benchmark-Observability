# Benchmark & Observability Report — Day 14

> Mọi con số ở các mục 2 và 3 được chép từ `reports/*.json` (bản gốc ở `06-lab-complete/benchmark-observability/develop/reports/`, bản sao ở `reports/`).
> Các mục 4, 5, 6 thuộc CP8 và còn để trống.

**Họ tên:** Nguyen Minh Phuc (MSSV 2A202603894)
**Ngày chạy:** 2026-11-26
**Môi trường:** MacBook Intel Core i5-8257U (8 luồng), RAM 8 GB, macOS 15.7, Python 3.13, agent chạy local bằng `python app.py` (một process uvicorn, không Docker). Máy lúc đó còn chạy các tác vụ khác song song nên số đo ở concurrency cao có nhiễu.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Mặc định của `load_test.py`. Latency bình thường ~150-250 ms, 500 ms là gấp đôi mức đó nên người dùng chưa thấy chậm |
| Error rate `/ask` | < 2 % | Mock LLM cố ý lỗi 1% (`MOCK_ERROR_RATE`), 2% chừa biên cho dao động mẫu 300 request |
| Accuracy trên golden dataset | ≥ 100 % (CI gate) | Golden dataset chỉ 23 câu nên mỗi câu sai là hơn 4 điểm %; gate đặt 100% và chặn cả regression so với baseline |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

Lệnh: `python load_test.py --url http://localhost:8002 --requests 300 --concurrency <c> --out reports/load_v2_c<c>.json`

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.02 | 194.7 | 247.3 | 1717.3 | 0.67% (2/300) | PASS |
| 10 | 38.29 | 195.1 | 232.5 | 1685.8 | 1.67% (5/300) | PASS |
| 50 | 50.46 | 288.4 | 2871.4 | 4052.4 | 1.67% (5/300) | FAIL |
| 100 | 41.67 | 1107.9 | 5275.6 | 5456.9 | 1.33% (4/300) | FAIL |

**Nhận xét:** RPS tăng gần tuyến tính từ concurrency 1 lên 10 (4.02 lên 38.29, gấp khoảng 9.5 lần) vì mỗi request chủ yếu chờ `asyncio.sleep` của mock LLM, nên nhiều request chạy chồng lên nhau. Sau đó không tăng nữa: c=50 đạt 50.46 rồi c=100 giảm còn 41.67. p50 và p95 tăng vọt (p95 từ 232.5 ms ở c=10 lên 2871.4 ms ở c=50 và 5275.6 ms ở c=100) và SLO p95 FAIL ở c=50 và c=100. Vì chỉ có một process uvicorn trên máy chung với các tác vụ khác nên request phải xếp hàng; điểm bão hòa nằm giữa c=10 và c=50. Tôi chưa tách riêng nguyên nhân (CPU của app hay CPU của chính `load_test.py` trên cùng máy) nên không khẳng định thêm. Error rate quanh 0.67-1.67% là lỗi 503 do `MOCK_ERROR_RATE=0.01`, không tăng theo concurrency, SLO error rate đều PASS.

### 2.2 Tail latency

Lệnh: khởi động lại v2 với `MOCK_SLOW_RATE=<rate>`, rồi `--requests 300 --concurrency 20 --out reports/load_v2_slow_<rate>.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 193.5 | 222.8 | 244.7 |
| 0.03 (mặc định) | 269.8 | 537.4 | 1717.7 |
| 0.1 | 369.0 | 1699.6 | 1722.6 |

**Nhận xét:** p99 là chỉ số nhạy nhất với request chậm: chỉ cần 3% request chậm thêm 1500 ms thì p99 nhảy từ 244.7 lên 1717.7 ms trong khi avg chỉ tăng từ 193.5 lên 269.8 ms. Khi tỉ lệ chậm là 10% (hơn 5%) thì cả p95 cũng lên 1699.6 ms còn avg mới 369.0 ms. Với 0.03, p95 = 537.4 ms đã vượt SLO 500 ms (mẫu 300 request nên p95 nằm sát ranh giới 5%). Average che giấu nhóm người dùng bị chậm: số trung bình vẫn "nghe ổn" trong khi 1 trong 10 người chờ gần 1.7 s. Vì vậy SLO đặt theo p95/p99 chứ không theo average.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Lệnh: `python eval/run_eval.py --url http://localhost:8001 --out reports/eval_v1.json`; `... --url http://localhost:8002 --baseline reports/eval_v1.json --out reports/eval_v2.json`; sau khi sửa KB: `... --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2.json --out reports/eval_v2_fixed.json`. Quality gate của v1 và v2 là mặc định (accuracy ≥ 80%), của bản sửa là 100%.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 57.1 | 109.3 | 113.6 |
| Tổng cost (USD) | 0.000404 | 0.000764 | 0.00079 |
| Cost / câu đúng (USD) | 0.00040395 | 3.639e-05 | 3.436e-05 |
| Latency p50 / p95 (ms, 23 câu) | 155.8 / 188.3 | 198.5 / 225.1 | 194.6 / 223.3 |
| Quality gate | FAIL (80%) | PASS (80%) | PASS (100%) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 | token, hết hạn, chữ ký | Không có entry nào khớp câu hỏi JWT nên v2 trả câu generic. Thêm entry `["jwt", "api key"]` vào `KNOWLEDGE_BASE` nói JWT là token có chữ ký và hết hạn, API key là chuỗi tĩnh |
| scaling-03 | cpu, memory, custom metrics | Thêm entry `["hpa", "kubernetes"]` nói HPA scale theo CPU, memory hoặc custom metrics |

Chỉ sửa `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và chép cùng 2 entry sang `production/utils/mock_llm.py`), không đụng `golden_dataset.jsonl`. Sau khi sửa v2 đạt 23/23, `--baseline` báo 0 regression.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:** v2 tốn 1.91 lần token mỗi câu (57.1 lên 109.3) vì prompt có thêm context từ retrieval, nên tổng cost cũng cao hơn (0.000404 lên 0.000764 USD). Đổi lại accuracy tăng từ 4.3% lên 91.3% và 100% sau khi sửa KB. Tính trên mỗi câu đúng, cost / câu đúng giảm từ 0.00040395 xuống 3.639e-05 USD (rẻ hơn khoảng 11.1 lần), và còn 3.436e-05 USD sau khi sửa (khoảng 11.8 lần). Latency p50 trong eval 23 câu là 155.8 ms (v1) so với 198.5 ms (v2), tức v2 chậm hơn một chút do bước retrieval; mẫu 23 câu quá nhỏ để kết luận về p95 nên latency phải dựa vào load test.

**Quality gate trong CI (Exercise 7.3):** file `.github/workflows/eval-gate.yml` chạy khi có pull request vào `main`: cài Python 3.11, khởi động agent v2 nền (`AGENT_VERSION=v2 PORT=8002`, `MOCK_ERROR_RATE=0` để eval không dính lỗi ngẫu nhiên), chờ `/health` trả 200, rồi chạy `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0`. `run_eval.py` thoát với exit code 0 khi accuracy đạt ngưỡng và không có regression, thoát với 1 khi accuracy dưới `--min-accuracy` hoặc có câu từng đúng nay sai (với `--baseline`). GitHub Actions coi exit code khác 0 là step fail nên job `eval-gate` fail. Để biến việc đó thành chặn merge, vào Settings, Branches, thêm branch protection rule cho `main`, bật "Require status checks to pass before merging" và chọn check `eval-gate`. Khi đó nút Merge bị khóa cho tới khi eval xanh, nên một thay đổi prompt, model hay knowledge base làm giảm chất lượng không vào được `main`. Workflow chưa được chạy trên GitHub trong CP7 này; chỉ kiểm tra các lệnh tương đương ở local.

**Cần hiểu:**

- *Vì sao đặt SLO theo p95/p99 chứ không theo trung bình?* Trung bình bị kéo bởi số đông request nhanh và che đuôi chậm. Ở bảng 2.2 với `MOCK_SLOW_RATE=0.03`, avg chỉ 269.8 ms nhưng p99 = 1717.7 ms; với 0.1 thì avg 369.0 ms mà p95 đã 1699.6 ms. Người dùng thật cảm nhận request chậm nhất của mình, nên SLO phải bám vào đuôi phân phối.
- *Vì sao "cost / câu đúng" tốt hơn "cost / câu" để so hai phiên bản?* Cost / câu chỉ tính tiền bỏ ra, không tính được gì. v1 rẻ hơn mỗi câu (57.1 so với 109.3 token) nhưng chỉ đúng 1/23 câu, nên tiền gần như bị phí. Cost / câu đúng chia tổng cost cho số câu đạt (0.00040395 cho v1 so với 3.639e-05 cho v2) nên phản ánh đúng giá của một kết quả dùng được; bản đắt hơn mỗi câu vẫn có thể rẻ hơn rất nhiều khi tính theo câu đúng.

---

## 4. Observability stack (production)

_CP8 — pending._ (Exercise 7.4–7.7 và scale_1 / scale_3 chạy ở CP8; điền sau.)

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

_CP8 — pending._ (Exercise 7.4–7.7 và scale_1 / scale_3 chạy ở CP8; điền sau.)

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
