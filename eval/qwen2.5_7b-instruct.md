# Evaluation: qwen2.5:7b-instruct, 96 synthetic tickets

| metric | value |
|---|---|
| category accuracy (all tickets) | 85.4% |
| urgency accuracy | 83.3% |
| language accuracy | 100.0% |
| automation rate (routed without a human) | 100.0% (96/96) |
| category accuracy of auto-routed tickets | 85.4% |
| correct team for auto-routed tickets | 94.8% |
| sent to human review | 0 |
| median seconds per ticket | 5.3 |
| personal data items masked | 33 |

Most frequent confusions (true -> predicted): other -> product_question (6), payment_invoice -> return_refund (3), other -> order_change (3), assembly_help -> damaged_item (2)
