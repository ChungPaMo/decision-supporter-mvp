"""뜻 판단을 서버(CPU)에 올릴 수 있는지 본다: 장치별 속도와 메모리, 더 작은 모델로 바꿨을 때의 정확도.

    python -X utf8 modules/file_classifier/tools/eval_speed.py [--json 결과.json] [--skip-small]

torch, transformers 가 필요하다. 작은 모델(intfloat/multilingual-e5-small)은 처음 실행할 때 Hugging Face 에서 내려받는다.
재는 것
    - 모델을 올리는 시간, 기준 용어를 숫자로 바꾸는 시간
    - 프로세스 메모리(Windows 에서만). 한 프로세스에서 여러 모델을 차례로 올리므로 앞 모델의 몫이 섞인다. 모델별 메모리로 읽으면 안 된다
    - 파일 하나를 뜻으로 판단하는 시간 (파일마다 낱말을 처음 보는 것으로 치고 잰다. 중앙값과 95% 지점)
    - 값 낱말(품목 코드, 날짜 등)을 빼기 전과 뺀 뒤
    - 정확도: 더미 test 109개(이 양식을 보기 전의 사전 + 뜻), 더미 200개(지금의 사전 + 뜻)
작은 모델은 유사도 분포가 달라 기준(0.65)을 그대로 쓸 수 없다. 여러 기준을 넣어 보고 모두 적는다.
이 109개로 기준을 고르므로 작은 모델의 수치는 유리하게 나온 값이다. 합성 자료이며 실제 기업 파일이 아니다.
"""
from __future__ import annotations

import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "modules" / "file_classifier" / "tools"), str(ROOT / "modules" / "file_classifier" / "src"), str(ROOT)]

import eval_embed as ee  # noqa: E402
import sort_folder as sf  # noqa: E402
from file_classifier import doctype, doctype_embed as de  # noqa: E402

SMALL = "intfloat/multilingual-e5-small"


def memory_mib() -> float | None:
    """지금 프로세스가 쓰는 메모리(working set). Windows 가 아니면 None."""
    try:
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

        c = Counters()
        c.cb = ctypes.sizeof(c)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return None
        del handle
        return round(c.WorkingSetSize / 2**20, 1)
    except Exception:
        return None


class MeanEmbedder:
    """E5 계열: 'query: ' 를 앞에 붙이고 토큰 평균을 쓴다."""

    def __init__(self, model: str, device: str):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self.torch, self.device = torch, device
        self.tok = AutoTokenizer.from_pretrained(model)
        self.model = AutoModel.from_pretrained(model).eval().to(device)

    def encode(self, texts, batch_size: int = 64):
        import numpy as np

        out = []
        with self.torch.no_grad():
            for i in range(0, len(texts), batch_size):
                enc = self.tok(["query: " + t for t in texts[i:i + batch_size]], padding=True, truncation=True, max_length=64, return_tensors="pt").to(self.device)
                hidden = self.model(**enc).last_hidden_state
                mask = enc["attention_mask"].unsqueeze(-1).float()
                pooled = (hidden * mask).sum(1) / mask.sum(1)
                out.append(self.torch.nn.functional.normalize(pooled.float(), dim=-1).cpu().numpy())
        return np.concatenate(out)


def tally(pred, gold) -> dict:
    ok = sum(p == g for p, g in zip(pred, gold))
    review = sum(p == de.REVIEW and p != g for p, g in zip(pred, gold))
    missed = sum(p == doctype.UNKNOWN and p != g for p, g in zip(pred, gold))
    return {"n": len(gold), "ok": ok, "review": review, "missed": missed, "wrong": len(gold) - ok - review - missed}


def main() -> None:
    import torch

    items = json.loads((ee.SAMPLES / "labels.json").read_text(encoding="utf-8"))["files"]
    sheets = [sf.read_sheets(ee.SAMPLES / "inbox" / it["file"]) for it in items]
    gold = [it["category"] for it in items]
    test = [i for i, it in enumerate(items) if it["split"] == "test"]
    current = [doctype.classify_workbook(s) for s in sheets]
    saved = doctype.KEYWORDS, doctype.EXACT
    doctype.KEYWORDS, doctype.EXACT = ee.legacy_rules()
    legacy = [doctype.classify_workbook(s) for s in sheets]
    doctype.KEYWORDS, doctype.EXACT = saved
    keep_filter = de.is_value_like
    results = []

    def run(label, make_embedder, device, tau=de.TAU, value_filter=True, timing=True):
        de.is_value_like = keep_filter if value_filter else (lambda term: False)
        before = memory_mib()
        t0 = time.perf_counter()
        embedder = make_embedder()
        load_s = time.perf_counter() - t0
        saved_min = de.MIN_SCORE
        de.MIN_SCORE = 2 * tau                             # combine() 이 읽는 값도 같은 기준으로 맞춘다
        t0 = time.perf_counter()
        matcher = de.SemanticMatcher(embedder, tau=tau, min_score=2 * tau)
        concept_s = time.perf_counter() - t0
        matcher.classify(sheets[0])                         # 첫 호출의 준비 시간은 빼고 잰다
        per_file, sem = [], []
        for s in sheets:
            matcher._cache.clear()                          # 파일마다 낱말을 처음 보는 것으로 친다
            t0 = time.perf_counter()
            sem.append(matcher.classify(s))
            per_file.append((time.perf_counter() - t0) * 1000)
        row = {"label": label, "device": device, "tau": tau, "value_filter": value_filter,
               "terms_per_file": round(statistics.mean(len(de.workbook_terms(s)) for s in sheets), 1),
               "load_s": round(load_s, 2), "concepts_s": round(concept_s, 2),
               "ms_median": round(statistics.median(per_file), 1), "ms_p95": round(sorted(per_file)[int(len(per_file) * 0.95) - 1], 1),
               "memory_mib": memory_mib(), "memory_before_mib": before,
               "test": tally([de.combine(legacy[i], sem[i])[0] for i in test], [gold[i] for i in test]),
               "all": tally([de.combine(v, s)[0] for v, s in zip(current, sem)], gold)}
        de.MIN_SCORE = saved_min
        de.is_value_like = keep_filter
        results.append(row)
        t = row["test"]
        print(f"{label:<34} {device:<4} 기준 {tau:<5} 낱말 {row['terms_per_file']:>5} | 올리기 {row['load_s']:>6}s 기준용어 {row['concepts_s']:>5}s "
              f"파일당 {row['ms_median']:>7}ms (95% {row['ms_p95']:>7}ms) 메모리 {row['memory_mib']}MiB | test {t['ok']}/{t['review']}/{t['missed']}/{t['wrong']} "
              f"all {row['all']['ok']}/{row['all']['review']}/{row['all']['missed']}/{row['all']['wrong']}", flush=True)
        del matcher, embedder
        return row

    print(f"파일 {len(items)}개 (test {len(test)}), torch {torch.__version__}, CPU 스레드 {torch.get_num_threads()}. 정확도 표기: 맞음/확인 필요/놓침/틀림")
    if torch.cuda.is_available():
        run("BGE-M3, 값 낱말 넣음", lambda: de.Embedder("cuda"), "cuda", value_filter=False)
        run("BGE-M3, 값 낱말 뺌", lambda: de.Embedder("cuda"), "cuda")
        torch.cuda.empty_cache()
    run("BGE-M3, 값 낱말 넣음", lambda: de.Embedder("cpu"), "cpu", value_filter=False)
    run("BGE-M3, 값 낱말 뺌", lambda: de.Embedder("cpu"), "cpu")
    if "--skip-small" not in sys.argv:
        for tau in (0.86, 0.88, 0.90, 0.92):
            run("multilingual-e5-small", lambda: MeanEmbedder(SMALL, "cpu"), "cpu", tau=tau)
    if "--json" in sys.argv:
        out = pathlib.Path(sys.argv[sys.argv.index("--json") + 1])
        out.write_text(json.dumps({"torch": torch.__version__, "cpu_threads": torch.get_num_threads(), "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                                   "bge": de.MODEL, "small": SMALL, "runs": results}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
