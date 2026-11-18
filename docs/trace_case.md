# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID trong report `reports/eval_seeded_regression.json` |
| Triệu chứng | Grader `trial_pass` fail (`status resolved != denied`); reply nói hoàn 20.000đ và ledger ghi 20.000đ trong khi nhãn kỳ vọng hoàn 0đ (denied) |
| Bước sai đầu tiên | **Event #3**: `model_override` `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event #1 (`handoff`) và Event #2 (`investigator` gọi `lookup_order`) hoàn toàn đúng, DB trả về `order.delay_days = 2`. Nhưng đến bước 3, agent bị lừa bởi lời khai trong ticket ("giao trễ 5 ngày") và sinh ra sự kiện `model_override` đè số ngày trễ từ 2 thành 5. |
| Failure mode | **FM-03** (`ticket_trust` — tin ticket hơn DB) |
| Đối chứng | Cùng claim C-002@11 trên shape `fixed`: Không hề có event `model_override`. Event #3 là `quote` trả về `amount_vnd = 0` (`no_entitlement`) và kết luận `denied` chuẩn xác. |
| Regression test | Grader `DbFactKept` (kiểm tra không có event `model_override`) và `RefundAmountCorrect` (bắt số tiền 20.000đ khác 0đ); test case `tests/test_lab9_graders.py::test_override_event_breaks_db_fact` bắt được lỗi này. |
| Chưa chắc chắn | Trace chỉ ghi nhận hành vi override từ MockLLM prompt logic, chưa khẳng định được với LLM thật bên ngoài có tự động sửa đổi nếu không có guardrail cứng ở tầng tool hay không. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
