"""취득 해시 매니페스트 CSV 내보내기(chain-of-custody 표준 산출물) 테스트.
attestation_csv(순수 직렬화) + GET /api/attestation.csv(라우트 배선).
read-only·무손실(acquired 그대로)·결정성·RFC-4180 인용 보증."""
import csv
import io


def _att(acquired):
    return {"acquired": acquired, "acquired_count": len(acquired),
            "stat_only_count": 0, "all_read_only": True, "modes_seen": ["rb"],
            "write_delete_rename_ops": 0, "note": "x"}


def test_attestation_csv_bom_and_header():
    from clfx.web.api import attestation_csv
    out = attestation_csv(_att([]))
    assert out.startswith("﻿")                 # Excel 한글 자동인식용 UTF-8 BOM
    first = out.lstrip("﻿").splitlines()[0]
    assert first == "path,algorithm,sha256"


def test_attestation_csv_rows_match_acquired():
    from clfx.web.api import attestation_csv
    acq = [{"path": "/a/x.jsonl", "sha256": "aa11"},
           {"path": "/b/y.jsonl", "sha256": "bb22"}]
    out = attestation_csv(_att(acq))
    rows = list(csv.reader(io.StringIO(out)))        # BOM은 reader가 첫 셀에 흡수 → utf-8-sig 무관
    rows[0][0] = rows[0][0].lstrip("﻿")
    assert rows[0] == ["path", "algorithm", "sha256"]
    assert rows[1] == ["/a/x.jsonl", "SHA-256", "aa11"]
    assert rows[2] == ["/b/y.jsonl", "SHA-256", "bb22"]
    assert len(rows) == 3                            # 헤더 + 2행 (무손실: 1 acquired = 1 행)


def test_attestation_csv_rfc4180_quoting_roundtrip():
    # 경로에 콤마/따옴표/개행 있어도 RFC-4180 인용으로 무손실 왕복.
    from clfx.web.api import attestation_csv
    nasty = '/path/with,comma and "quote"/z.jsonl'
    out = attestation_csv(_att([{"path": nasty, "sha256": "cc33"}]))
    rows = list(csv.reader(io.StringIO(out.lstrip("﻿"))))
    assert rows[1][0] == nasty                       # 원본 경로 그대로 복원
    assert rows[1][2] == "cc33"


def test_attestation_csv_empty_only_header():
    from clfx.web.api import attestation_csv
    out = attestation_csv(_att([])).lstrip("﻿")
    lines = [ln for ln in out.splitlines() if ln]
    assert lines == ["path,algorithm,sha256"]        # 데이터 행 0


def test_attestation_csv_deterministic():
    from clfx.web.api import attestation_csv
    a = _att([{"path": "/a", "sha256": "1"}, {"path": "/b", "sha256": "2"}])
    assert attestation_csv(a) == attestation_csv(a)  # 재실행 동일


def test_attestation_csv_handles_none():
    from clfx.web.api import attestation_csv
    assert attestation_csv(None).lstrip("﻿").splitlines()[0] == "path,algorithm,sha256"


def test_api_attestation_csv_route():
    # GET /api/attestation.csv → 200·text/csv·attachment. 라우트 배선 + 헤더 증명.
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from clfx.web.server import make_handler, ServerState
    from clfx.query.engine import QueryEngine
    state = ServerState(QueryEngine([]))
    state.attestation = _att([{"path": "/ev/log.jsonl", "sha256": "deadbeef"}])
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/attestation.csv") as r:
            code = r.status
            ctype = r.headers.get("Content-Type")
            disp = r.headers.get("Content-Disposition")
            body = r.read().decode("utf-8")
        assert code == 200
        assert ctype == "text/csv; charset=utf-8"
        assert disp == 'attachment; filename="acquisition-hash-manifest.csv"'
        rows = list(csv.reader(io.StringIO(body.lstrip("﻿"))))
        assert rows[0] == ["path", "algorithm", "sha256"]
        assert rows[1] == ["/ev/log.jsonl", "SHA-256", "deadbeef"]
    finally:
        httpd.shutdown()
