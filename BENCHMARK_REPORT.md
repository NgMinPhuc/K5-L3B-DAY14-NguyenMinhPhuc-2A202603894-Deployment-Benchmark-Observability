# Benchmark & Observability Report — Day 14

> Mọi con số ở các mục 2 và 3 được chép từ `reports/*.json` (bản gốc ở `06-lab-complete/benchmark-observability/develop/reports/`, bản sao ở `reports/`).
> Các mục 4, 5, 6 (CP8) lấy từ `benchmark-results/*.csv`, log agent và Prometheus API của stack Docker.

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

**Quality gate trong CI (Exercise 7.3):** file `.github/workflows/eval-gate.yml` chạy khi có pull request vào `main`: cài Python 3.11, khởi động agent v2 nền (`AGENT_VERSION=v2 PORT=8002`, `MOCK_ERROR_RATE=0` để eval không dính lỗi ngẫu nhiên), chờ `/health` trả 200, rồi chạy `python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0`. `run_eval.py` thoát với exit code 0 khi accuracy đạt ngưỡng và không có regression, thoát với 1 khi accuracy dưới `--min-accuracy` hoặc có câu từng đúng nay sai (với `--baseline`). GitHub Actions coi exit code khác 0 là step fail nên job `eval-gate` fail. Để biến việc đó thành chặn merge, vào Settings, Branches, thêm branch protection rule cho `main`, bật "Require status checks to pass before merging" và chọn check `eval-gate`. Khi đó nút Merge bị khóa cho tới khi eval xanh, nên một thay đổi prompt, model hay knowledge base làm giảm chất lượng không vào được `main`. Workflow đã chạy thật trên pull request CP7 và job `eval-gate` PASS (19s).

**Cần hiểu:**

- *Vì sao đặt SLO theo p95/p99 chứ không theo trung bình?* Trung bình bị kéo bởi số đông request nhanh và che đuôi chậm. Ở bảng 2.2 với `MOCK_SLOW_RATE=0.03`, avg chỉ 269.8 ms nhưng p99 = 1717.7 ms; với 0.1 thì avg 369.0 ms mà p95 đã 1699.6 ms. Người dùng thật cảm nhận request chậm nhất của mình, nên SLO phải bám vào đuôi phân phối.
- *Vì sao "cost / câu đúng" tốt hơn "cost / câu" để so hai phiên bản?* Cost / câu chỉ tính tiền bỏ ra, không tính được gì. v1 rẻ hơn mỗi câu (57.1 so với 109.3 token) nhưng chỉ đúng 1/23 câu, nên tiền gần như bị phí. Cost / câu đúng chia tổng cost cho số câu đạt (0.00040395 cho v1 so với 3.639e-05 cho v2) nên phản ánh đúng giá của một kết quả dùng được; bản đắt hơn mỗi câu vẫn có thể rẻ hơn rất nhiều khi tính theo câu đúng.

---

## 4. Observability stack (production)

Stack chạy bằng `docker compose -p k5-day14-observability up -d --build --scale agent=1` trong `06-lab-complete/benchmark-observability/production/` (Docker Desktop, 6 container: agent, nginx, prometheus, grafana, jaeger, locust). Giờ ghi bên dưới là UTC của ngày 2026-11-26 (máy local là UTC+7).

**Sửa Dockerfile để chạy được:** lần build đầu agent crash-loop với `ModuleNotFoundError: No module named 'uvicorn'`. Nguyên nhân: user `agent` có home `/app` nên Python tìm package ở `/app/.local`, trong khi stage builder chép package vào `/home/agent/.local`. Tôi thêm dòng `ENV PYTHONUSERBASE=/home/agent/.local` vào `production/Dockerfile`, sau đó agent chạy bình thường.

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải: `screenshots/grafana-dashboard.png` (dashboard "Day 14 — AI Agent Overview", 15 phút gần nhất, thấy Golden Signals, LLM latency, tokens/s, cost)
- [x] Một trace chậm trong Jaeger: `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger (span `chat` có event `exception`): `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với 2 alert cùng **firing**: `screenshots/prometheus-alert-firing.png` (`AgentHighErrorRate` và `AgentHighLatencyP95`, nhóm `agent-slo` hiện "FIRING (2)")

### 4.2 Exercise 7.4: trả lời câu hỏi

1. **p95 và avg:** ở ảnh Grafana panel "Latency p95" đọc được 324.47 ms (agent v2, `MOCK_LATENCY_MS=120`). Trong Locust scale 3 instance (mục 5) avg của `/ask` là 255.8 ms còn p95 là 370 ms, p99 là 1700 ms. Khoảng cách giữa avg/p50 và p95/p99 cho thấy đa số request nhanh (p50 = 200 ms) nhưng có một nhóm nhỏ rất chậm (`MOCK_SLOW_RATE=0.03` thêm khoảng 1.5 s); avg che nhóm này nên SLO dùng p95/p99.
2. **Panel "Requests/s theo instance":** có hai đường (`172.28.0.7:8000` và `172.28.0.8:8000`) với đỉnh gần như chồng lên nhau (khoảng 30 req/s mỗi instance lúc tải cao nhất) nên Nginx chia khá đều (round-robin mặc định). Lưu ý: ảnh này chụp trong một lần chạy mà sau này tôi phát hiện chỉ có 2 instance (xem mục 5), nên panel "Instances up" hiện 2 chứ không phải 3.
3. **Input tokens/s lớn hơn output tokens/s:** prompt gồm câu hỏi cộng ngữ cảnh lấy từ bước retrieval, còn câu trả lời ngắn. Ví dụ dòng log `llm_call` của trace chậm ở mục 4.4: `input_tokens` 73, `output_tokens` 35. Trên ảnh, đỉnh input khoảng 6.6K/s so với output khoảng 4.3K/s.
4. **`curl http://localhost:8080/metrics`:** theo `production/nginx/nginx.conf` có `location = /metrics { return 404; }`, tức Nginx trả 404. Lý do được ghi trong file: metric lộ thông tin hệ thống, route, lưu lượng nên chỉ Prometheus scrape trực tiếp trong mạng nội bộ. (Tôi đọc từ cấu hình, chưa chạy lệnh curl này trước khi dọn stack.)

### 4.3 Thí nghiệm "phá hệ thống"

Tải nền: Locust headless 30 user (`--no-deps`). Đổi cấu hình bằng biến môi trường khi `docker compose up -d --scale agent=3` (compose tạo lại 3 container). Thời gian lấy từ vòng poll `http://localhost:9090/api/v1/alerts` mỗi 3 giây.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` (đổi lúc 09:27:39) | `AgentHighErrorRate`: pending 09:28:33, firing 09:29:34 | 115 s (khoảng 1 phút pending theo `for: 1m`, cộng thời gian recreate container và cửa sổ `rate[1m]`) | Error rate |
| B | thêm `MOCK_SLOW_RATE=0.3` (đổi lúc 09:30:42, giữ `MOCK_ERROR_RATE=0.2`) | `AgentHighLatencyP95`: pending 09:31:30, firing 09:33:27 | 165 s (`for: 2m` cộng thời gian p95 vượt 1 s) | Latency p50/p95/p99 |
| C | `LLM_MODEL=mock-llm-large` | Không làm | | |
| D | `docker pause` 1 instance | Không làm | | |
| E | `AGENT_VERSION=v1` | Không làm | | |

Ở thời điểm chụp ảnh Alerts (khoảng 09:34) cả hai alert cùng firing; sau đó đo nhanh bằng PromQL: error rate `/ask` 0.186 (18.6%, ngưỡng 5%) và p95 `/ask` 4.50 s (ngưỡng 1 s). Alert `LLMCostBurnRateHigh` cũng firing từ 09:14:57 đến khoảng 09:28:30 nhưng do tải 100 user của lần chạy Locust trước (burn rate trên $2/giờ, panel Cost trên ảnh Grafana đã vượt đường $2), không phải do thí nghiệm. `AgentInstanceDown` chỉ nhảy sang pending ngắn mỗi lần compose tạo lại container rồi về inactive, không bao giờ firing.

**Phân tích:** hai thí nghiệm cho thấy alert không firing ngay khi sự cố bắt đầu mà phải qua `pending` đủ thời gian `for`, nên độ trễ phát hiện là 115 s và 165 s; đổi lại tránh báo động giả khi chỉ có một spike. Thí nghiệm B diễn ra khi A vẫn firing nên hai alert độc lập nhau và hiện cùng lúc. Với C, D, E tôi không chạy nên không có số liệu để báo cáo.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?** (chưa chạy E, trả lời theo lý thuyết) Đổi sang v1 chỉ làm mất bước retrieval, không làm lỗi HTTP hay latency tăng, nên các alert hạ tầng không thấy gì. Theo CP7, v1 chỉ đúng 4.3% (1/23) so với 91.3% của v2 (`reports/eval_v1.json`, `reports/eval_v2.json`), tức chỉ eval trên golden dataset (chạy định kỳ hoặc trên bản canary, cộng quality gate trong CI) mới bắt được loại lỗi chất lượng này.

### 4.4 Debug bằng trace

Trace chậm (Jaeger, service `observable-agent`, chọn trace có thời gian dài nhất trong 1500 trace gần nhất lúc đó):

- `trace_id`: `9ee3897f14875b1d0304629a550245cb`
- Tổng thời gian: 1849.7 ms (`POST /ask`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1690.3 ms, khoảng 91% tổng). Các span còn lại: `agent.run` 1759.8 ms, `agent.retrieve_context` 69.1 ms
- Dòng log tương ứng (grep theo `trace_id` trong `docker compose -p k5-day14-observability logs agent`):

```json
{"ts": "2026-11-26T09:24:11.065090+00:00", "level": "INFO", "service": "observable-agent", "instance": "a6fe4f487aef", "event": "llm_call", "trace_id": "9ee3897f14875b1d0304629a550245cb", "span_id": "a71615f30666d068", "request_id": "942b2e7f29da", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 73, "output_tokens": 35, "cost_usd": 3.2e-05, "llm_ms": 1689.1}
{"ts": "2026-11-26T09:24:11.065980+00:00", "level": "INFO", "service": "observable-agent", "instance": "a6fe4f487aef", "event": "http_request", "trace_id": "9ee3897f14875b1d0304629a550245cb", "span_id": "a71615f30666d068", "request_id": "942b2e7f29da", "method": "POST", "route": "/ask", "status": 200, "ms": 1848.9}
```

Trace lỗi (`screenshots/jaeger-error-trace.png`): `trace_id` `de0ff314c3e6e7c115d4ef2e802b2762`, `POST /ask` 862.8 ms trả 503; span `chat mock-llm-small` 838.7 ms có status error và event `exception` ("LLMError: Upstream LLM error: 503 Service Unavailable (mock)"). Dòng log cùng `trace_id`:

```json
{"ts": "2026-11-26T09:24:14.917074+00:00", "level": "INFO", "service": "observable-agent", "instance": "890cd19f9bc8", "event": "llm_error", "trace_id": "de0ff314c3e6e7c115d4ef2e802b2762", "span_id": "c8f8c19f6ee405d1", "request_id": "2bdd976f234d", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
{"ts": "2026-11-26T09:24:14.917450+00:00", "level": "INFO", "service": "observable-agent", "instance": "890cd19f9bc8", "event": "http_request", "trace_id": "de0ff314c3e6e7c115d4ef2e802b2762", "span_id": "c8f8c19f6ee405d1", "request_id": "2bdd976f234d", "method": "POST", "route": "/ask", "status": 503, "ms": 862.1}
```

Kết luận từ trace: chậm hoặc lỗi nằm ở span gọi LLM (upstream), không phải ở code retrieval hay code agent.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số lấy từ dòng `Aggregated` của `benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv` (bản gốc ở `06-lab-complete/benchmark-observability/production/benchmark-results/`). Mỗi instance giới hạn `cpus: 0.5`, `memory: 256M`.

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 32.35 | 800 | 7600 | 11000 | 116 / 3798 (3.05%) |
| 3 | 64.65 | 200 | 350 | 1700 | 66 / 7682 (0.86%) |

Dòng `/ask` riêng (cùng file CSV): 1 instance có avg 1746.4 ms, 29.37 req/s, 116 lỗi (504: 58, 503: 36, 502: 22); 3 instance có avg 255.8 ms, 58.95 req/s, 66 lỗi (đều 503).

**Giải thích kết quả:** scale từ 1 lên 3 instance cải thiện rõ: RPS gấp khoảng 2.0 lần (32.35 lên 64.65), p95 giảm từ 7600 ms xuống 350 ms và số lỗi giảm. Với 1 instance giới hạn 0.5 CPU, 100 user vượt khả năng xử lý nên request xếp hàng và Nginx trả 504/502 (lỗi ở tầng load balancer, xem README mục 2.6 bài D). Với 3 instance p95 350 ms gần với latency nền của mock LLM, tức agent hết nghẽn; p99 1700 ms còn lại là nhóm request chậm cố ý (`MOCK_SLOW_RATE=0.03`, mỗi request chậm thêm ~1.5 s) và không giảm được bằng cách thêm instance. Lỗi 503 còn lại là lỗi giả lập (`MOCK_ERROR_RATE=0.01`). RPS không tăng gấp 3 vì Locust có `wait_time` 0.5-2 s nên tổng tải bị giới hạn bởi 100 user, không phải bởi khả năng của stack.

**Lưu ý phương pháp:** lệnh trong CHECKPOINTS (`docker compose run --rm locust ...`) mặc định đồng bộ lại service phụ thuộc theo `deploy.replicas: 2` trong `docker-compose.yml`, nên lần chạy đầu của tôi bị lệch: ở lần "1 instance" compose thêm instance thứ hai khi Locust bắt đầu, và ở lần "3 instance" compose xóa instance thứ ba khoảng 35 giây sau khi bắt đầu (thấy qua `docker events` và `count(up{job="agent"})` trong Prometheus). Tôi bỏ cả hai bộ CSV đó và chạy lại với `docker compose -p k5-day14-observability run --no-deps --rm locust ...` sau khi chờ đủ số container (1 rồi 3, đều `healthy`). Bộ CSV nộp là của lần chạy lại này. Ảnh Grafana ở mục 4.1 chụp trong lần chạy lệch nên chỉ có 2 instance.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. Đuôi phân phối quan trọng hơn trung bình: ở scale 3 instance avg `/ask` là 255.8 ms nhưng p99 là 1700 ms (`scale_3_stats.csv`); ở develop v2 với `MOCK_SLOW_RATE=0.03` avg 269.8 ms mà p99 1717.7 ms (`reports/load_v2_slow_0.03.json`). SLO phải đặt theo p95/p99.
  2. Thêm instance giải quyết nghẽn tài nguyên chứ không giải quyết latency của upstream: p95 giảm từ 7600 ms xuống 350 ms khi scale 1 lên 3, nhưng p99 vẫn 1700 ms vì request chậm nằm ở span `chat mock-llm-small` (1690.3 ms trong trace `9ee3897f...`). Trace chỉ ra đúng nơi chậm, log theo `trace_id` cho chi tiết request đó.
  3. Alert có độ trễ có chủ đích, và công cụ đo cũng có thể sai: error rate 0.2 mất 115 s và p95 mất 165 s mới firing; lệnh benchmark ban đầu còn đo sai số instance vì `docker compose run` khôi phục `replicas: 2`, nên phải đối chiếu `docker events` hoặc số target `up` trước khi tin con số. Lỗi chất lượng (v1 chỉ đúng 4.3%, `reports/eval_v1.json`) không làm alert hạ tầng nào đỏ, cần eval riêng.
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa? Thêm alert ở tầng Nginx/load balancer (tỉ lệ 502/503/504 và độ trễ phía client) vì lỗi 502/504 ở scale 1 instance không được metric của agent đếm; một synthetic check từ bên ngoài; chỉ số chất lượng chạy định kỳ (accuracy eval trên golden dataset) với alert khi tụt dưới ngưỡng; `AgentInstanceDown` cần bắt cả trường hợp container biến mất khỏi DNS (hiện chỉ bắt được trường hợp `docker pause`); và Alertmanager để gửi cảnh báo thật thay vì chỉ xem trang Alerts.
