"""Strict allow-list for tools exposed to the language model."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from app.ai import tools as application_tools
from app.ai.gateway import AIToolError, AIValidationError


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler_name: str

    def openai_schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name, "description": self.description,
                "parameters": self.input_model.model_json_schema(), "strict": False}}


class ToolRegistry:
    """A closed registry: model output can never select arbitrary Python code."""
    def __init__(self) -> None:
        self._tools = {
            "search_properties": RegisteredTool("search_properties", "Search verified catalogue records using deterministic filters and ranking.", application_tools.SearchInput, "search_properties"),
            "search_web_properties": RegisteredTool("search_web_properties", "Discover property listings from the web via the configured search provider. Results are web-discovered (not verified) and must be cited by result_id.", application_tools.SearchWebInput, "search_web_properties"),
            "get_property": RegisteredTool("get_property", "Get verified details for specified property IDs.", application_tools.PropertyIdsInput, "get_property"),
            "nearby_places": RegisteredTool("nearby_places", "Get current provider nearby places for one property.", application_tools.NearbyInput, "find_nearby_places"),
            "route": RegisteredTool("route", "Get an actual configured-provider route between coordinates.", application_tools.RouteInput, "calculate_route"),
            "compare_properties": RegisteredTool("compare_properties", "Compare 2-4 properties using verified catalogue records and deterministic price estimates.", application_tools.PropertyIdsInput, "compare"),
            "calculate_affordability": RegisteredTool("calculate_affordability", "Compute affordable loan amount and EMI from monthly income (deterministic).", application_tools.AffordInput, "calculate_affordability"),
            "calculate_emi": RegisteredTool("calculate_emi", "Compute monthly EMI for a loan (deterministic).", application_tools.EmiInput, "calculate_emi"),
            "calculate_rental_yield": RegisteredTool("calculate_rental_yield", "Compute gross/net rental yield for a property (deterministic).", application_tools.YieldInput, "calculate_rental_yield"),
            "calculate_roi": RegisteredTool("calculate_roi", "Project investment return over N years (deterministic).", application_tools.RoiInput, "calculate_roi"),
        }

    def definitions(self) -> list[dict]:
        return [tool.openai_schema() for tool in self._tools.values()]

    def execute(self, db, user, name: str, arguments: str | dict) -> tuple[dict, float]:
        tool = self._tools.get(name)
        if not tool:
            raise AIValidationError("The requested AI tool is not allowed")
        try:
            data = json.loads(arguments) if isinstance(arguments, str) else arguments
            if not isinstance(data, dict):
                raise ValueError("arguments must be an object")
            validated = tool.input_model.model_validate(data)
        except (ValueError, TypeError, ValidationError) as exc:
            raise AIValidationError(f"Invalid arguments for {name}") from exc
        started = time.perf_counter()
        try:
            result = application_tools.execute_tool(db, user, tool.handler_name, validated.model_dump())
        except PermissionError as exc:
            raise AIValidationError("You are not authorized to use that tool") from exc
        except Exception as exc:
            raise AIToolError(f"{name} could not complete") from exc
        return result, round((time.perf_counter() - started) * 1000, 1)
