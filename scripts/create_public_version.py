from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public_release"

EXCLUDED_PATHS = {
    "app/broker",
    "app/strategy",
    "app/worker",
    "app/services/kis",
    "app/market/realtime",
    "app/market/provider",
    "app/api/router_order.py",
    "app/api/router_order_query.py",
    "app/api/router_rebalance.py",
    "app/api/router_account.py",
    "app/api/router_realtime.py",
    "app/repository",
    "tests",
}

INCLUDE_TOP_LEVEL = [
    "README.md",
    "pyproject.toml",
    "poetry.lock",
    "docker-compose.yml",
    "docker-compose.dev.yml",
    "Dockerfile",
    "app",
]

SAFE_MAIN = '''from fastapi import FastAPI\n\napp = FastAPI(title="Auto Trading System (Public Release)", version="0.1.0-public")\n\n\n@app.get("/")\nasync def root() -> dict[str, str]:\n    return {"message": "Public release - core trading modules are removed."}\n\n\n@app.get("/health")\nasync def health() -> dict[str, str]:\n    return {"status": "ok"}\n'''

SAFE_ROUTER = '''from fastapi import APIRouter\n\nrouter = APIRouter()\n'''

REMOVED_NOTE = '''# Removed For Open Source\n\n이 경로는 오픈소스 공개 버전에서 제거되었습니다.\n\n제거 기준:\n- 브로커 연동 세부 구현\n- 주문/체결 핵심 로직\n- 전략/리밸런싱 로직\n- 실시간 시세 처리 핵심 로직\n- 내부 테스트 자산\n'''


def should_exclude(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return any(rel == ex or rel.startswith(ex + "/") for ex in EXCLUDED_PATHS)


def copy_item(src: Path, dst: Path) -> None:
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            if should_exclude(child):
                continue
            copy_item(child, dst / child.name)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def write_removed_markers() -> None:
    for ex in sorted(EXCLUDED_PATHS):
        ex_path = Path(ex)
        if ex_path.suffix:  # file path
            marker = OUT / ex_path.parent / f"{ex_path.name}.REMOVED.md"
        else:  # directory path
            marker = OUT / ex_path / "REMOVED_FOR_OPEN_SOURCE.md"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(REMOVED_NOTE, encoding="utf-8")


def override_safe_files() -> None:
    (OUT / "app" / "main.py").write_text(SAFE_MAIN, encoding="utf-8")
    (OUT / "app" / "api" / "router.py").write_text(SAFE_ROUTER, encoding="utf-8")


if __name__ == "__main__":
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)

    for name in INCLUDE_TOP_LEVEL:
        src = ROOT / name
        if not src.exists() or should_exclude(src):
            continue
        copy_item(src, OUT / name)

    write_removed_markers()
    override_safe_files()

    (OUT / "PUBLIC_RELEASE_NOTICE.md").write_text(
        """# Public Release Notice\n\n이 폴더는 공개용으로 핵심 매매 모듈을 제거한 버전입니다.\n원본 저장소의 구조를 일부 유지하되, 민감/핵심 구현은 포함하지 않습니다.\n\n재생성:\n```bash\npython scripts/create_public_version.py\n```\n""",
        encoding="utf-8",
    )

    print(f"Public release generated at: {OUT}")
