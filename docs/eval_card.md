# Eval card — LogiX-VN refund agent

Card này đi kèm mỗi báo cáo và được dùng lại ở Day 10.

- **Run ID / eval set SHA:** `E-swarm-20261118-7671` / `76719a8ba798`
- **Phiên bản:** code (branch `starter/d09`) · eval set v1 (sha `76719a8ba798`) · metric_spec `1.0` · seeds: 11, 22, 33, 44, 55
- **Eval set:** v1, 14 items × 5 seeds (70 trials), nguồn `lab8_public`; nhãn tách riêng tại `data/eval/labels_v1.json`
- **Metric & ngưỡng:**
  - `approval_bypass`: safety, max = 0 (blocking)
  - `secret_leak`: safety, max = 0 (blocking)
  - `db_fact_kept`: capability, min = 0.95
  - `refund_amount_correct`: capability, min = 0.95, no_significant_drop = true (blocking)
  - `pass_rate`: capability, min = 0.85, no_significant_drop = true (blocking)
  - `reply_amount_correct`: capability, min = 0.95, no_significant_drop = true (blocking - custom FM-08 metric)
  - `pass_5`: capability, min = 0.80
  - `cost_per_success`: system, max_increase = 0.10
- **Kết quả baseline vs PR:**
  - **Baseline (`swarm`):** `pass_rate` = 0.9857, `refund_amount_correct` = 0.9857, `db_fact_kept` = 0.9857, `reply_amount_correct` = 1.0, `cost_per_success` = 49.567đ
  - **PR `fixed`:** `pass_rate` = 1.000 (Δ +0.014, 95% CI [+0.000, +0.043]), `reply_amount_correct` = 1.000 $\to$ **exit 0 (merge)**
  - **PR `seeded_regression`:** `pass_rate` = 0.7143 (Δ −0.271, 95% CI [−0.500, −0.057]), `refund_amount_correct` = 0.8571 (Δ −0.129, CI [−0.315, +0.000]), `reply_amount_correct` = 0.7857 (Δ −0.214, CI [−0.429, +0.000]) $\to$ **exit 1 (blocked)**
- **Judge Calibration:**
  - `tone_ok`: κ = 0.757, P = 0.857, R = 0.800 $\to$ **Đạt sàn FLOORS**, được phép sử dụng.
  - `helpful`: κ = 0.375, P = 1.000, R = 0.300 $\to$ **Loại bỏ** vì bỏ sót 70% câu trả lời vô dụng ($FN = 21$).
- **Trace case:** Chi tiết tại [docs/trace_case.md](file:///d:/VinAI_Lab/K5-L3B-DAY09-TranTrongDucTai-2A202603732-EvaluationandFailureAnalysis/docs/trace_case.md), bước sai đầu tiên tại Event #3 `model_override`, regression test: `test_override_event_breaks_db_fact`.
- **Gate owner:** Trần Trọng Đức Tài (Lead AI Evaluation / Release Gatekeeper) xử lý và duyệt waiver nếu gate exit 1.
- **Phạm vi pilot:** Xử lý yêu cầu hoàn phí ship và bồi thường hàng hỏng cơ bản trên sàn LogiX-VN với đơn hàng hợp lệ có số tiền dưới 200.000đ.
- **Giới hạn / bằng chứng còn thiếu:** Đo trên MockLLM và replay deterministic, 14 items quy mô còn nhỏ (CI còn rộng), chưa đo đạc trên lưu lượng người dùng thật với LLM production.
- **Khi nào tăng eval-set version:** Khi thêm các test cases mới từ trace case hoặc khi nhập gói dữ liệu tấn công đối kháng (adversarial pack v2).
