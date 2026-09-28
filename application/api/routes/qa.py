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
    summary="Valida reglas deterministas de calidad",
    description="Mismo motor `SubtitleQA` que la CLI: errores, avisos, "
    "hallazgos y política estricta opcional.",
)
async def qa(
    file: UploadFile = File(description="Archivo .srt/.vtt/.ass/.ssa/.txt"),  # noqa: B008
    strict: Annotated[
        Optional[bool],
        Form(description="Falla también ante cualquier aviso"),  # noqa: B008
    ] = False,
) -> QAReportModel:
    suffix = validate_extension(file.filename)
    tmp_path = await save_upload(file, suffix)
    try:
        service = new_service()
        try:
            qa_report = service.qa_file(str(tmp_path))
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=400, detail="archivo no encontrado"
            ) from exc
        except (OSError, UnicodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=safe_detail(exc)) from exc
        payload = qa_report.to_dict()
        if strict and not qa_report.strict_passed:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"QA estricto: {payload['error_count']} errores, "
                    f"{payload['warning_count']} avisos"
                ),
            )
        return QAReportModel(**payload)
    finally:
        remove_temp(tmp_path)
