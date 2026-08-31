import json
import logging
import os

from odoo import fields

from .fake_provider import FakeProvider
from .openai_provider import OpenAiProvider
from .prompts import MESSAGE_ANALYSIS_PROMPT_VERSION, MEETING_ANALYSIS_PROMPT_VERSION
from .owner_resolver import resolve_user

_logger = logging.getLogger(__name__)


class IntelligenceService:
    def __init__(self, env): self.env = env
    def _provider(self): return OpenAiProvider() if os.getenv("PPA_AI_PROVIDER", "fake") == "openai" else FakeProvider()
    def _failed(self, analysis, error):
        _logger.warning("PPA AI analysis %s failed: %s", analysis.id, error)
        analysis.write({"status": "failed", "error_message": str(error)[:500], "processed_at": fields.Datetime.now()})
        return analysis
    def analyze_message(self, message):
        provider = self._provider()
        analysis = self.env["ppa.ai.analysis"].create({"name": "AI analysis: %s" % message.name, "source_type": "message", "message_id": message.id, "provider": provider.name, "model": "fake" if provider.name == "fake" else os.getenv("PPA_OPENAI_MODEL", ""), "prompt_version": MESSAGE_ANALYSIS_PROMPT_VERSION, "status": "processing"})
        try:
            result = provider.analyze_message(message); self._validate_message(result)
            analysis.write({"status":"completed","summary":result["summary"],"category":result["category"],"importance":result["importance"],"requires_reply":result["requires_reply"],"requires_action":result["requires_action"],"suggested_flow":result.get("suggested_flow"),"suggested_project":result.get("suggested_project"),"suggested_owner":result.get("suggested_owner"),"reasoning_summary":result.get("reasoning_summary"),"confidence":result["confidence"],"raw_response_json":json.dumps(result),"processed_at":fields.Datetime.now()})
            message.write({"ai_processed":True,"ai_summary":result["summary"],"ai_category":result["category"],"ai_importance":result["importance"],"ai_confidence":result["confidence"],"ai_reasoning_summary":result.get("reasoning_summary"),"requires_reply":result["requires_reply"],"requires_action":result["requires_action"]})
            self._resolve_message_context(message, result)
            for action in result.get("suggested_actions", []): self.env["ppa.suggested.action"].create({"name":action["title"],"description":action.get("description"),"priority":action.get("priority","normal"),"due_date":self._due_date(action.get("due_date")),"raw_deadline_text":action.get("due_date") if not self._due_date(action.get("due_date")) else False,"source_type":"message","source_message_id":message.id,"ai_analysis_id":analysis.id,"ai_confidence":action.get("confidence",0),"ai_reason":action.get("reason")})
            return analysis
        except Exception as error: return self._failed(analysis, error)
    def _resolve_message_context(self, message, result):
        conversation = message.conversation_id
        if not conversation:
            return
        flow = conversation.flow_id
        if not flow and result.get("suggested_flow"):
            flows = self.env["ppa.flow"].search([("name", "=ilike", result["suggested_flow"])])
            flows = flows.filtered(lambda item: self._same_name(item.name, result["suggested_flow"]))
            if len(flows) == 1:
                conversation.flow_id = flows.id
                flow = flows
        if flow and flow.project_id and not conversation.project_id:
            conversation.project_id = flow.project_id.id
        if not conversation.project_id and result.get("suggested_project"):
            projects = self.env["project.project"].search([("name", "=ilike", result["suggested_project"])])
            projects = projects.filtered(lambda item: self._same_name(item.name, result["suggested_project"]))
            if len(projects) == 1:
                conversation.project_id = projects.id
        values = {}
        if not message.flow_id and conversation.flow_id: values["flow_id"] = conversation.flow_id.id
        if not message.project_id and conversation.project_id: values["project_id"] = conversation.project_id.id
        if not message.owner_id and result.get("suggested_owner"):
            owner = resolve_user(self.env, result["suggested_owner"])
            if owner: values["owner_id"] = owner.id
        if values: message.write(values)
    @staticmethod
    def _same_name(left, right):
        return " ".join((left or "").split()).casefold() == " ".join((right or "").split()).casefold()
    def analyze_meeting(self, meeting):
        provider=self._provider(); analysis=self.env["ppa.ai.analysis"].create({"name":"AI analysis: %s"%meeting.name,"source_type":"meeting","meeting_id":meeting.id,"provider":provider.name,"model":"fake" if provider.name=="fake" else os.getenv("PPA_OPENAI_MODEL",""),"prompt_version":MEETING_ANALYSIS_PROMPT_VERSION,"status":"processing"})
        try:
            result=provider.analyze_meeting(meeting); self._validate_meeting(result)
            analysis.write({"status":"completed","summary":result["summary"],"importance":result["importance"],"confidence":result["confidence"],"raw_response_json":json.dumps(result),"processed_at":fields.Datetime.now()})
            meeting.write({"ai_processed":True,"ai_summary":result["summary"],"ai_importance":result["importance"],"ai_confidence":result["confidence"]})
            for item in result.get("decisions",[]): self.env["ppa.decision"].create({"name":item["title"],"description":item.get("description"),"responsible_user_id":resolve_user(self.env,item.get("responsible_user")).id,"responsible_user_text":item.get("responsible_user"),"source_type":"meeting","source_meeting_id":meeting.id,"ai_analysis_id":analysis.id})
            for item in result.get("suggested_actions",[]): self.env["ppa.suggested.action"].create({"name":item["title"],"priority":item.get("priority","normal"),"suggested_user_id":resolve_user(self.env,item.get("suggested_user")).id,"suggested_user_text":item.get("suggested_user"),"source_type":"meeting","source_meeting_id":meeting.id,"ai_analysis_id":analysis.id,"ai_confidence":item.get("confidence",0),"ai_reason":item.get("reason")})
            for item in result.get("open_questions",[]): self.env["ppa.open.question"].create({"name":item["question"],"meeting_id":meeting.id,"ai_analysis_id":analysis.id,"suggested_user_id":resolve_user(self.env,item.get("owner")).id,"suggested_user_text":item.get("owner"),"importance":item.get("importance","normal"),"confidence":item.get("confidence",0),"company_id":meeting.company_id.id,"project_id":meeting.project_id.id})
            return analysis
        except Exception as error: return self._failed(analysis, error)
    def _due_date(self,value):
        try: return fields.Datetime.to_datetime(value) if value else False
        except (TypeError,ValueError): return False
    def _validate_message(self,result):
        self._validate_base(result, True)
    def _validate_meeting(self,result):
        self._validate_base(result, False)
        for key,title in (("decisions","title"),("suggested_actions","title"),("open_questions","question")):
            if not isinstance(result.get(key,[]),list): raise ValueError("Invalid meeting list.")
            for item in result[key]:
                if not isinstance(item,dict) or not item.get(title) or not 0 <= float(item.get("confidence",0)) <= 1: raise ValueError("Invalid meeting item.")
    def _validate_base(self,result,message):
        priorities=dict(self.env["ppa.suggested.action"]._fields["priority"].selection)
        if not isinstance(result,dict) or not isinstance(result.get("summary"),str) or result.get("importance") not in priorities or not 0 <= float(result.get("confidence",-1)) <= 1: raise ValueError("Invalid structured analysis.")
        if message and result.get("category") not in dict(self.env["ppa.ai.analysis"]._fields["category"].selection): raise ValueError("Invalid category.")
