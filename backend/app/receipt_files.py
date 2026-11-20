"""Validate receipt attachments and retain their transaction history."""

import base64
import binascii
from hashlib import sha256
from io import BytesIO
from urllib.parse import quote
import warnings

from fastapi import Depends, HTTPException, Request, Response
from PIL import Image
import psycopg
from pydantic import BaseModel, Field, ValidationError

MAX_BYTES = 5_000_000
MAX_PIXELS = 24_000_000
METADATA = """r.id,r.purchase_id,r.original_name,r.media_type,r.sha256,r.uploaded_at,r.uploaded_by,
 r.replaces_id,r.replacement_reason,octet_length(r.contents) AS bytes"""


class ReceiptUpload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4 * ((MAX_BYTES + 2) // 3))
    replaces_id: int | None = Field(default=None, gt=0)
    reason: str = Field(default="", max_length=1000)


async def bounded_upload(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 6_700_000:
            raise HTTPException(413, "Receipt upload exceeds the 5 MB file limit")
        body.extend(chunk)
    try:
        return ReceiptUpload.model_validate_json(body)
    except ValidationError:
        raise HTTPException(422, "Invalid receipt file or details") from None


def decode(upload):
    name = upload.name.strip()
    if not name or name in (".", "..") or any(char in "/\\" or not char.isprintable() for char in name):
        raise HTTPException(422, "Invalid receipt file name")
    try:
        data = base64.b64decode(upload.content, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(422, "Invalid receipt file encoding") from None
    if not 1 <= len(data) <= MAX_BYTES:
        raise HTTPException(422, "Receipt files must be between 1 byte and 5 MB")
    # PDFs are stored as opaque attachments and always downloaded, never rendered by the app.
    if data.startswith((b"%PDF-1.", b"%PDF-2.0")) and data.rstrip().endswith(b"%%EOF"):
        return name, "application/pdf", data
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=("PNG", "JPEG")) as image:
                if image.width * image.height > MAX_PIXELS or getattr(image, "n_frames", 1) != 1:
                    raise ValueError
                media_type = Image.MIME[image.format]
                image.verify()
            with Image.open(BytesIO(data), formats=("PNG", "JPEG")) as image:
                image.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, "Choose a valid PDF, single-image JPEG or PNG receipt") from None
    return name, media_type, data


def register_receipts(router, db, audit, staff):
    @router.get("/transactions/{purchase_id}/files")
    def list_files(purchase_id: int):
        with db() as connection:
            if not connection.execute("SELECT 1 FROM purchase WHERE id=%s", (purchase_id,)).fetchone():
                raise HTTPException(404, "Purchase not found")
            return connection.execute(f"""SELECT {METADATA}, successor.id AS replaced_by
                FROM purchase_receipt_file r LEFT JOIN purchase_receipt_file successor ON successor.replaces_id=r.id
                WHERE r.purchase_id=%s ORDER BY r.id DESC""", (purchase_id,)).fetchall()

    @router.post("/transactions/{purchase_id}/files", status_code=201)
    def add_file(purchase_id: int, upload: ReceiptUpload = Depends(bounded_upload), username: str = Depends(staff)):
        reason = upload.reason.strip()
        if upload.replaces_id is not None and not reason:
            raise HTTPException(422, "Give a reason for replacing the receipt")
        if upload.replaces_id is None and reason:
            raise HTTPException(422, "Select the receipt you are replacing")
        name, media_type, data = decode(upload)
        digest = sha256(data).hexdigest()
        try:
            with db() as connection:
                if not connection.execute("SELECT 1 FROM purchase WHERE id=%s FOR UPDATE", (purchase_id,)).fetchone():
                    raise HTTPException(404, "Purchase not found")
                duplicate = connection.execute("SELECT purchase_id FROM purchase_receipt_file WHERE sha256=%s", (digest,)).fetchone()
                if duplicate:
                    raise HTTPException(409, f"An identical receipt is already attached to purchase #{duplicate['purchase_id']}")
                if upload.replaces_id is not None and not connection.execute("""SELECT 1 FROM purchase_receipt_file r
                    WHERE r.id=%s AND r.purchase_id=%s
                    AND NOT EXISTS (SELECT 1 FROM purchase_receipt_file successor WHERE successor.replaces_id=r.id)""",
                    (upload.replaces_id, purchase_id),
                ).fetchone():
                    raise HTTPException(409, "Choose a current receipt linked to this purchase")
                saved = connection.execute(f"""INSERT INTO purchase_receipt_file AS r
                    (purchase_id,original_name,media_type,sha256,contents,uploaded_by,replaces_id,replacement_reason)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {METADATA}""",
                    (purchase_id, name, media_type, digest, data, username, upload.replaces_id, reason or None),
                ).fetchone()
                audit(connection, "receipt_replaced" if upload.replaces_id else "receipt_uploaded", "purchase",
                      purchase_id, {"receipt_id": saved["id"], "replaces_id": upload.replaces_id, "reason": reason or None})
                return saved | {"replaced_by": None}
        except psycopg.errors.UniqueViolation as error:
            if error.diag.constraint_name == "purchase_receipt_file_sha256_key":
                raise HTTPException(409, "An identical receipt was just uploaded") from None
            raise

    @router.get("/transactions/{purchase_id}/files/{file_id}")
    def download_file(purchase_id: int, file_id: int):
        with db() as connection:
            receipt = connection.execute("""SELECT original_name,media_type,contents FROM purchase_receipt_file
                WHERE purchase_id=%s AND id=%s""", (purchase_id, file_id)).fetchone()
        if not receipt:
            raise HTTPException(404, "Receipt file not found")
        extension = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}[receipt["media_type"]]
        return Response(receipt["contents"], media_type="application/octet-stream", headers={
            "Content-Disposition": f"attachment; filename=receipt-{file_id}.{extension}; filename*=UTF-8''" +
                quote(receipt["original_name"].rsplit(".", 1)[0] + "." + extension, safe=""),
        })
