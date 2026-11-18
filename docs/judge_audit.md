# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt (κ=0.757 ≥ 0.6, P=0.857 ≥ 0.8, R=0.800 ≥ 0.7) | dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không đạt (κ=0.375 < 0.6, Recall=0.300 < 0.7) | loại |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú & Hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 (`Em đã hoàn tiền cho anh rồi nha, anh check giúp em.`) | PASS | FAIL | Người đúng | Xưng hô "em - anh" quá suồng sã, không theo quy chuẩn dịch vụ khách hàng B2C ("LogiX - anh/chị"). **Sửa rubric:** Thêm quy tắc cấm đại từ nhân xưng thân mật gia đình vào danh mục vi phạm tone. |
| 2 | H-017 (`Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha.`) | PASS | FAIL | Người đúng | Dùng từ đệm "bạn ơi", "nha" thiếu tính trang trọng, chuyên nghiệp. **Sửa rubric:** Bổ sung ví dụ cụ thể về các hư từ/thán từ suồng sã cần tránh trong prompt của judge. |
| 3 | H-029 (`Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm.`) | PASS | FAIL | Người đúng | Giọng điệu cộc lốc, mệnh lệnh xua đuổi khách hàng ("không cần nhắn thêm"). **Sửa rubric:** Đưa tiêu chí "thái độ thiếu tôn trọng / cấm cản khách hàng giao tiếp" thành tiêu chuẩn FAIL rõ ràng. |
| 4 | H-042 (`Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ.`) | FAIL | PASS | Người đúng | Câu văn chuẩn mực, có thông tin rõ ràng về timeline nhận tiền. Judge bị nhầm lẫn khắt khe quá mức (False Positive). **Sửa rubric:** Làm rõ việc cung cấp thông tin dự kiến thời gian xử lý không phải là lỗi giọng điệu. |
| 5 | H-051 (`Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ.`) | FAIL | PASS | Cả hai có lý | Câu văn lịch sự nhưng chèn từ tiếng Anh "refund". Judge gán FAIL vì tiếng bồi, còn con người chấp nhận được trong ngữ cảnh thương mại điện tử. **Sửa rubric:** Quy định nhất quán xem có chấp nhận thuật ngữ phổ biến ("refund", "order") hay bắt buộc thuần Việt 100%. |
| 6 | HL-016 (`Dạ, LogiX thành thật xin lỗi anh/chị vì sự bất tiện này...`) | PASS | FAIL | Người đúng | Câu trả lời chỉ xin lỗi sáo rỗng (apology template) nhưng hoàn toàn không đưa ra giải pháp hay tiến độ cho khiếu nại. Judge bị đánh lừa bởi sự lịch sự mà quên mất tính hữu ích (Helpfulness). |

## Kết luận
- **Tiêu chí bị loại:** `judge_helpful` bị loại vì ma trận nhầm lẫn cho thấy $FN = 21$ (Recall chỉ đạt $0.3$, $\kappa = 0.375$). Judge bỏ lọt tới 70% các câu trả lời vô dụng chỉ vì chúng chứa văn mẫu xin lỗi lịch sự. Nếu dùng judge này làm gate release, agent không hữu ích vẫn sẽ lọt qua dễ dàng.
- **Tiêu chí được chọn:** `judge_tone` đạt đủ cả 3 tiêu chuẩn sàn (FLOORS): $\kappa = 0.757 \ge 0.6$, $P = 0.857 \ge 0.8$, $R = 0.800 \ge 0.7$. Tỷ lệ lỗi quan sát $28\%$ qua hiệu chỉnh Rogan-Gladen phản ánh đúng tỷ lệ lỗi thực tế $30\%$.
- **Rủi ro còn lại:** Judge mới chỉ được kiểm định trên tập dữ liệu replay công khai có sẵn; cần thu thập thêm nhãn con người mới để làm tập held-out độc lập trong môi trường production.
