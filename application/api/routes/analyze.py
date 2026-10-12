"""Analyze endpoint: same SubtitleAnalyticsService result as the CLI."""

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..deps import (
    new_service,
    remove_temp,
    safe_detail,
    save_upload,
    validate_extension,
)
from ..schemas import AnalyzeResponse

router = APIRouter(tags=["analyze"])


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Analyze a subtitle file",
    description="Return grouped content, timing, quality, and "
    "processing metrics along with the deterministic QA report.",
)
async def analyze(
    file: UploadFile = File(  # noqa: B008
        description="Subtitle file (.srt/.vtt/.ass/.ssa/.txt)"
    ),
) -> AnalyzeResponse:
    suffix = validate_extension(file.filename)
    tmp_path = await save_upload(file, suffix)
    try:
        service = new_service()
        try:
            analytics, qa_report = service.analyze_file(str(tmp_path))
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=400, detail="file not found"
            ) from exc
        except (OSError, UnicodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=safe_detail(exc)) from exc
        return AnalyzeResponse(
            analytics=analytics.to_dict(),  # type: ignore[arg-type]
            qa=qa_report.to_dict(),  # type: ignore[arg-type]
        )
    finally:
        remove_temp(tmp_path)
