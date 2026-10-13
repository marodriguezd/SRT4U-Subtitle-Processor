"""QA endpoint: the exact deterministic engine used by the CLI."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from typing import Annotated, Optional

from ..deps import (
    new_service,
    remove_temp,
    safe_detail,
    save_upload,
    validate_extension,
)
from ..schemas import QAReportModel

router = APIRouter(tags=["qa"])


@router.post(
    "/qa",
    response_model=QAReportModel,
    summary="Validate deterministic quality rules",
    description="Same `SubtitleQA` engine as the CLI: errors, warnings, "
    "findings, and optional strict gating.",
)
async def qa(
    file: UploadFile = File(description="Subtitle file (.srt/.vtt/.ass/.ssa/.txt)"),  # noqa: B008
    strict: Annotated[
        Optional[bool],
        Form(description="Fail on warnings as well as errors"),  # noqa: B008
    ] = False,
) -> QAReportModel:
    suffix = validate_extension(file.filename)
    tmp_path = await save_upload(file, suffix)
    try:
        service = new_service()
        try:
            qa_report = service.qa_file(str(tmp_path))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail="file not found") from exc
        except (OSError, UnicodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=safe_detail(exc)) from exc
        payload = qa_report.to_dict()
        if strict and not qa_report.strict_passed:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Strict QA: {payload['error_count']} errors, "
                    f"{payload['warning_count']} warnings"
                ),
            )
        return QAReportModel(**payload)
    finally:
        remove_temp(tmp_path)
