"""서버가 쓰는 bytes 입력 경로(doctype_io)를 확인한다."""
import io

from openpyxl import Workbook

from file_classifier.doctype_io import REVIEW, classify_bytes


def xlsx(rows) -> bytes:
    wb = Workbook()
    for row in rows:
        wb.active.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_xlsx_bytes_are_classified():
    data = xlsx([["주간 생산현황표"], [], ["순번", "작업인원", "정품수량", "불량수량", "불량률", "불량원인"], [1, 8, 3000, 56, "1.83%", "엠보 불량"]])
    out = classify_bytes("자료.xlsx", data)
    assert out["category"] == "MES" and out["readable"] is True and out["evidence"]


def test_csv_bytes_are_classified():
    out = classify_bytes("a.csv", "수주일자,수주번호,거래처,품번,단가,공급가액,부가세\n2026-11-02,SO1,한빛마트,CP-1,7900,100,10\n".encode("utf-8-sig"))
    assert out["category"] == "ERP"


def test_broken_file_is_review_not_error():
    out = classify_bytes("broken.xlsx", b"not an excel file")
    assert out["category"] == REVIEW and out["readable"] is False and out["reason"]
