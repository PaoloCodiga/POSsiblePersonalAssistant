import hmac
import json
import logging
import os

from werkzeug.exceptions import BadRequest

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PpaApiController(http.Controller):
    def _json_response(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _authorized(self):
        configured_key = os.getenv("PPA_API_KEY", "")
        provided_key = request.httprequest.headers.get("X-PPA-API-Key", "")
        return bool(configured_key) and hmac.compare_digest(provided_key, configured_key)

    def _require_authorization(self):
        if self._authorized():
            return None
        return self._json_response({"error": "unauthorized"}, status=401)

    def _payload(self):
        if not request.httprequest.is_json:
            return None, self._json_response({"error": "Content-Type must be application/json."}, status=400)
        try:
            payload = request.httprequest.get_json(force=False, silent=False)
        except BadRequest:
            return None, self._json_response({"error": "Malformed JSON payload."}, status=400)
        if not isinstance(payload, dict):
            return None, self._json_response({"error": "The JSON payload must be an object."}, status=400)
        return payload, None

    def _source(self, code):
        if not code:
            return None
        return request.env["ppa.source"].sudo().search([("code", "=", code)], limit=1)

    @http.route("/ppa/api/health", type="http", auth="none", methods=["GET"], csrf=False)
    def health(self, **kwargs):
        unauthorized = self._require_authorization()
        if unauthorized:
            return unauthorized
        return self._json_response({"status": "ok", "application": "POSsible Personal Assistant", "version": "0.1.0"})

    @http.route("/ppa/api/messages", type="http", auth="none", methods=["POST"], csrf=False)
    def create_message(self, **kwargs):
        unauthorized = self._require_authorization()
        if unauthorized:
            return unauthorized
        payload, error = self._payload()
        if error:
            return error
        if not payload.get("source") or not payload.get("external_id"):
            return self._json_response({"error": "source and external_id are required."}, status=400)
        source = self._source(payload["source"])
        if not source:
            return self._json_response({"error": "Unknown PPA source."}, status=400)
        Message = request.env["ppa.message"].sudo()
        existing = Message.search([("source_id", "=", source.id), ("external_id", "=", payload["external_id"])], limit=1)
        if existing:
            return self._json_response({"id": existing.id, "status": "existing"})
        conversation = request.env["ppa.conversation"].sudo().browse()
        conversation_external_id = payload.get("conversation_external_id")
        if conversation_external_id:
            Conversation = request.env["ppa.conversation"].sudo()
            conversation = Conversation.search([("source_id", "=", source.id), ("external_id", "=", conversation_external_id)], limit=1)
            if not conversation:
                conversation = Conversation.create({"name": payload.get("subject") or conversation_external_id, "source_id": source.id, "external_id": conversation_external_id})
        record = Message.create({"name": payload.get("subject") or payload["external_id"], "source_id": source.id, "external_id": payload["external_id"], "conversation_id": conversation.id, "sender_name": payload.get("sender_name"), "sender_address": payload.get("sender_address"), "subject": payload.get("subject"), "body": payload.get("body"), "received_at": fields.Datetime.to_datetime(payload["received_at"]) if payload.get("received_at") else False, "raw_payload_json": json.dumps(payload.get("raw_payload", {}))})
        return self._json_response({"id": record.id, "status": "created"}, status=201)

    @http.route("/ppa/api/meetings", type="http", auth="none", methods=["POST"], csrf=False)
    def create_meeting(self, **kwargs):
        unauthorized = self._require_authorization()
        if unauthorized:
            return unauthorized
        payload, error = self._payload()
        if error:
            return error
        if not payload.get("source") or not payload.get("external_id"):
            return self._json_response({"error": "source and external_id are required."}, status=400)
        source = self._source(payload["source"])
        if not source:
            return self._json_response({"error": "Unknown PPA source."}, status=400)
        Meeting = request.env["ppa.meeting"].sudo()
        existing = Meeting.search([("source_id", "=", source.id), ("external_id", "=", payload["external_id"])], limit=1)
        if existing:
            return self._json_response({"id": existing.id, "status": "existing"})
        record = Meeting.create({"name": payload.get("name") or payload["external_id"], "source_id": source.id, "external_id": payload["external_id"], "started_at": fields.Datetime.to_datetime(payload["started_at"]) if payload.get("started_at") else False, "ended_at": fields.Datetime.to_datetime(payload["ended_at"]) if payload.get("ended_at") else False, "summary": payload.get("summary"), "transcript": payload.get("transcript"), "raw_payload_json": json.dumps(payload.get("raw_payload", {}))})
        return self._json_response({"id": record.id, "status": "created"}, status=201)

    @http.route("/ppa/api/suggested-actions", type="http", auth="none", methods=["POST"], csrf=False)
    def create_suggested_action(self, **kwargs):
        unauthorized = self._require_authorization()
        if unauthorized:
            return unauthorized
        payload, error = self._payload()
        if error:
            return error
        if not payload.get("name"):
            return self._json_response({"error": "name is required."}, status=400)
        source_type = payload.get("source_type", "manual")
        values = {"name": payload["name"], "description": payload.get("description"), "priority": payload.get("priority", "normal"), "due_date": fields.Datetime.to_datetime(payload["due_date"]) if payload.get("due_date") else False, "ai_confidence": payload.get("ai_confidence", 0), "ai_reason": payload.get("ai_reason"), "source_type": source_type, "state": "to_confirm"}
        if source_type == "message":
            message_domain = [("external_id", "=", payload.get("source_external_id"))]
            if payload.get("source"):
                source = self._source(payload["source"])
                if not source:
                    return self._json_response({"error": "Unknown PPA source."}, status=400)
                message_domain.append(("source_id", "=", source.id))
            message = request.env["ppa.message"].sudo().search(message_domain, limit=1)
            if not message:
                return self._json_response({"error": "Referenced source message was not found."}, status=404)
            values["source_message_id"] = message.id
        elif source_type != "manual":
            return self._json_response({"error": "Only manual and message source types are supported by this endpoint."}, status=400)
        record = request.env["ppa.suggested.action"].sudo().create(values)
        return self._json_response({"id": record.id, "status": "created", "state": record.state}, status=201)
