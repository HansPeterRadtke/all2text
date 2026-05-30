from __future__ import annotations

from email import policy
from email.parser import BytesParser
from pathlib import Path

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class EmailBackend:
    name = "email_metadata_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "email"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        if classification.concrete_format.upper() in {"EML", "MBOX"}:
            parsed, warnings = parse_email(path)
            limitation = "Email attachments are listed by metadata only; attached files are not recursively extracted."
            text = render_email(parsed, limitation)
            return ConversionResult(
                text=text,
                converter_used=self.name,
                extraction_methods_used=["stdlib_email_parse"],
                warnings=warnings,
                metadata={"email": parsed},
                limitations=[limitation],
            )
        limitation = "This email container format requires a specialist parser; core all2text records safe metadata only."
        return ConversionResult(
            text=binary_summary_text(
                path,
                classification,
                ctx,
                heading="Email safe summary",
                extra_lines=[f"- limitation: {limitation}"],
            ),
            converter_used=self.name,
            extraction_methods_used=["email_placeholder_summary"],
            limitations=[limitation],
        )


def parse_email(path: Path) -> tuple[dict[str, object], list[str]]:
    warnings: list[str] = []
    try:
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    except Exception as exc:
        return {}, [f"email_parse_failed:{exc}"]
    headers = {
        key: str(message.get(key, ""))
        for key in ["From", "To", "Cc", "Bcc", "Subject", "Date", "Message-ID", "MIME-Version", "Content-Type"]
        if message.get(key)
    }
    plain_parts: list[str] = []
    attachments: list[dict[str, object]] = []
    if message.is_multipart():
        for part in message.walk():
            disposition = part.get_content_disposition()
            content_type = part.get_content_type()
            filename = part.get_filename()
            if disposition == "attachment" or filename:
                payload = part.get_payload(decode=True) or b""
                attachments.append({"filename": filename, "content_type": content_type, "size_bytes": len(payload)})
                continue
            if content_type == "text/plain":
                try:
                    plain_parts.append(part.get_content())
                except Exception as exc:
                    warnings.append(f"email_part_decode_failed:{exc}")
    else:
        try:
            if message.get_content_type() == "text/plain":
                plain_parts.append(message.get_content())
        except Exception as exc:
            warnings.append(f"email_body_decode_failed:{exc}")
    return {
        "headers": headers,
        "plain_body": "\n".join(part for part in plain_parts if part),
        "attachment_count": len(attachments),
        "attachments": attachments,
    }, warnings


def render_email(parsed: dict[str, object], limitation: str) -> str:
    lines = ["Email message:", f"Limitation: {limitation}", "", "Headers:"]
    headers = parsed.get("headers")
    if isinstance(headers, dict) and headers:
        lines.extend(f"- {key}: {value}" for key, value in headers.items())
    else:
        lines.append("- none parsed")
    lines.extend(["", f"Attachments: {parsed.get('attachment_count', 0)}"])
    for attachment in parsed.get("attachments", []) if isinstance(parsed.get("attachments"), list) else []:
        lines.append(f"- {attachment}")
    body = str(parsed.get("plain_body") or "")
    lines.extend(["", "Plain text body:", body if body else "<none>"])
    return "\n".join(lines).rstrip() + "\n"

