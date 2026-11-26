# Day 14 Lab - Mission Answers

> K5-L3B · Day 14 · Deployment, Benchmark & Observability

---

## Part 1: Localhost vs Production

_CP1 — pending._

---

## Part 2: Docker

_CP2 — pending._

---

## Part 3: Cloud Deployment

_CP6 — pending._

---

## Part 4: API Security

_CP3 — pending._

---

## Part 5: Scaling & Reliability

> Ghi chú: cổng 8000 trên máy đang bị tiến trình khác chiếm nên Exercise 5.1–5.2 chạy bản develop bằng `PORT=8104 python app.py` (app đọc biến `PORT`), thay vì 8000. Python 3.13 trong venv ngoài repo. Stack Exercise 5.4 dùng cổng 8080 đúng như hướng dẫn.

### Exercise 5.1: Health và readiness

`05-scaling-reliability/develop/app.py` đã có sẵn cả hai endpoint. Chạy trên cổng 8104:

```
$ curl -s -w '\nHTTP %{http_code}\n' localhost:8104/health
{"status":"ok","uptime_seconds":2.6,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:56:45.782919+00:00","checks":{"memory":{"status":"ok","used_percent":66.4}}}
HTTP 200
$ curl -s -w '\nHTTP %{http_code}\n' localhost:8104/ready
{"ready":true,"in_flight_requests":1}
HTTP 200
```

- `/health` (liveness): "process còn sống không?". Nếu fail/timeout thì platform **restart** container. Chỉ nên kiểm tra bản thân process, không phụ thuộc dịch vụ ngoài.
- `/ready` (readiness): "đã sẵn sàng nhận traffic chưa?". Trả 503 khi đang khởi động (`_is_ready=False`), đang shutdown hoặc dependency (Redis/DB) chưa nối được. Load balancer **ngừng gửi traffic** nhưng không restart.
- (`in_flight_requests: 1` là chính request `/ready` đang được middleware đếm.)

### Exercise 5.2: Graceful shutdown

Gửi request chậm (mock LLM ngủ 3 giây) rồi `kill -TERM` sau 1 giây:

```
kill -TERM 21378
--- curl result
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
HTTP 200 time=3.083595s
--- log
INFO:     Shutting down
INFO:     127.0.0.1:51447 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
2026-11-26 14:56:53,528 INFO 🔄 Graceful shutdown initiated...
2026-11-26 14:56:53,529 INFO ✅ Shutdown complete
INFO:     Application shutdown complete.
INFO:     Finished server process [21378]
2026-11-26 14:56:53,530 INFO Received signal 15 — uvicorn will handle graceful shutdown
process exited
```

Request đang xử lý vẫn hoàn thành (HTTP 200 sau 3.08s) dù SIGTERM đến sau 1 giây; uvicorn ngừng nhận kết nối mới ("Shutting down"), chờ request xong rồi chạy phần shutdown của `lifespan` (đặt `_is_ready=False`, chờ `_in_flight_requests` về 0, tối đa 30s) rồi mới thoát. Nếu dùng SIGKILL thì request sẽ bị cắt ngang.

### Exercise 5.3: Stateless design

State trong RAM (ví dụ `conversation_history = {}`) hỏng khi chạy nhiều instance vì mỗi instance có bộ nhớ riêng: request 1 của user rơi vào instance A (lưu history ở A), request 2 qua load balancer rơi vào instance B thì B không thấy history, nên agent "mất trí nhớ". Instance bị restart/scale-down cũng mất toàn bộ state. Giải pháp: giữ state ở kho dùng chung (Redis); instance chỉ xử lý logic nên thay thế/nhân bản tuỳ ý. Bản `production/app.py` lưu session và history trong Redis (`/chat`, `/chat/{session_id}/history`).

### Exercise 5.4: Load balancing

```
$ touch .env.local   # đã gitignore, không commit
$ docker compose -p k5-day14-scaling up -d --build --scale agent=3
$ docker compose -p k5-day14-scaling ps
k5-day14-scaling-agent-1   Up (healthy)   8000/tcp
k5-day14-scaling-agent-2   Up (healthy)   8000/tcp
k5-day14-scaling-agent-3   Up (healthy)   8000/tcp
k5-day14-scaling-nginx-1   Up             0.0.0.0:8080->80/tcp
k5-day14-scaling-redis-1   Up (healthy)   6379/tcp
```

(Lần `up` đầu bị Docker Hub trả 429 khi pull `nginx:alpine`, thử lại sau vài phút thì được.) Gọi 10 lần `POST /chat` qua Nginx, in `session_id` (8 ký tự đầu), `served_by`, `turn`:

```
43f30ad1 instance-515807 2
e435c0a7 instance-746c62 2
dee79a7d instance-33a180 2
ec2ec373 instance-515807 2
ddd06134 instance-746c62 2
5b6cca11 instance-33a180 2
649c0b96 instance-515807 2
a04c4ad6 instance-746c62 2
e88ec627 instance-33a180 2
19071c9c instance-515807 2
```

Nginx chia request round-robin qua 3 instance (515807 → 746c62 → 33a180 → lặp lại). Mỗi lệnh curl không gửi `session_id` nên mỗi lần tạo một session mới. Nếu một instance chết, Nginx chuyển traffic sang các instance còn lại (không thử trong bài này).

### Exercise 5.5: Test stateless

```
$ python test_stateless.py
Session ID: b922babc-328b-4092-88ed-bbc359eb02c9
Request 1: [instance-746c62]  Q: What is Docker?
Request 2: [instance-33a180]  Q: Why do we need containers?
Request 3: [instance-515807]  Q: What is Kubernetes?
Request 4: [instance-746c62]  Q: How does load balancing work?
Request 5: [instance-33a180]  Q: What is Redis used for?
Total requests: 5
Instances used: {'instance-515807', 'instance-33a180', 'instance-746c62'}
✅ All requests served despite different instances!
--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

(Output rút gọn phần câu trả lời mock và danh sách 10 message.) Giải thích: 5 câu hỏi cùng một session được 3 instance khác nhau xử lý, nhưng khi đọc history có đủ 10 message (5 user + 5 assistant) vì state nằm trong Redis chứ không nằm trong RAM của instance nào. Script này không tự tắt instance nào, nên kết quả chứng minh state chia sẻ giữa các instance, chưa chứng minh sống sót khi instance chết. Cuối cùng chạy `docker compose -p k5-day14-scaling down` để trả cổng 8080.

---

## Part 6: Final Project — check_production_ready.py

_CP5 — pending._

---

## AI log

_Filled per checkpoint._
