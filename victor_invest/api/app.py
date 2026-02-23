# Copyright 2025 Vijaykumar Singh <singhvjd@gmail.com>
# SPDX-License-Identifier: Apache-2.0

"""FastAPI application for Victor Investment API.

This module provides REST API endpoints for investment analysis using
the Victor framework with StateGraph workflows.

Usage:
    uvicorn victor_invest.api.app:app --reload --port 8000

ARCHITECTURE: Victor-Core Integration
=====================================

This API replaces the old InvestiGator REST API with Victor-powered endpoints.
Key differences:

OLD (api/main.py):
- Custom AgentManager with event bus, Redis queues
- Manual agent orchestration
- Workflow IDs tracking state in Redis

NEW (victor_invest/api/app.py):
- StateGraph workflows from Victor framework
- Direct tool invocation (context stuffing pattern)
- In-memory job storage (Redis optional for production)

Endpoints migrated:
- POST /analyze/{symbol} - Single symbol analysis
- POST /batch - Batch analysis
- GET /batch/{job_id} - Batch status
- GET /health - Health check
- GET /cache/stats - Cache statistics
- POST /cache/warm - Warm cache
- DELETE /cache/symbol/{symbol} - Clear symbol cache
- GET /models - List available LLM models
"""

import asyncio
import csv
import io
import json
import logging
import math
import os
import re
import sys
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from victor_invest import __version__ as VICTOR_INVEST_VERSION

# Victor framework imports
try:
    from victor.framework import Agent
except ImportError:
    Agent = None

from victor_invest.workflows import (
    AnalysisMode,
)
from victor_invest.workflows import run_yaml_analysis as run_workflow_analysis

# Include sector analysis router
from victor_invest.api.sectors import router as sectors_router

logger = logging.getLogger(__name__)
ALLOWED_API_ANALYSIS_MODES = (
    AnalysisMode.QUICK.value,
    AnalysisMode.STANDARD.value,
    AnalysisMode.COMPREHENSIVE.value,
)
BATCH_ANALYSIS_MAX_PARALLEL = 4
UI_CACHE_DIR = Path("artifacts/ui_cache")
UI_LOG_SCAN_DIRS = (Path("artifacts/logs"), Path("."))
UI_MAX_LOG_FILE_BYTES = 5 * 1024 * 1024
UI_MAX_LOG_SCAN_FILES = 120


def _react_dist_dir() -> Path:
    """Resolved path to the React frontend build output."""
    env_override = os.environ.get("VICTOR_FRONTEND_DIR")
    if env_override:
        return Path(env_override).resolve()
    return Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


# ========================================================================================
# Application Lifecycle
# ========================================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle - startup and shutdown."""
    # Startup
    logger.info("Starting Victor Investment API...")

    # Initialize components
    app.state.analysis_jobs = {}
    app.state.cache_manager = None

    # Try to initialize cache manager
    try:
        from investigator.infrastructure.cache import CacheManager

        app.state.cache_manager = CacheManager()
        logger.info("Cache manager initialized")
    except Exception as e:
        logger.warning(f"Cache manager not available: {e}")

    # Try to initialize database
    try:
        from sqlalchemy import text

        from investigator.infrastructure.database import get_database_engine

        engine = get_database_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        app.state.db_engine = engine
        logger.info("Database engine initialized and connection verified")
    except Exception as e:
        logger.warning(f"Database not available: {e}")
        app.state.db_engine = None

    logger.info("Victor Investment API started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Victor Investment API...")

    # Cleanup
    if app.state.cache_manager:
        try:
            # Close cache if it has a close method
            if hasattr(app.state.cache_manager, "close"):
                await app.state.cache_manager.close()
        except Exception as e:
            logger.warning(f"Error closing cache: {e}")

    logger.info("Victor Investment API shutdown complete")


# ========================================================================================
# FastAPI Application
# ========================================================================================

app = FastAPI(
    title="Victor Investment API",
    description="Institutional-grade investment research API powered by Victor AI framework",
    version=VICTOR_INVEST_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include sector analysis router
app.include_router(sectors_router)

# Serve React frontend assets (JS/CSS bundles) if the build directory exists.
_react_assets = _react_dist_dir() / "assets"
if _react_assets.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount(
        "/ui/assets", StaticFiles(directory=str(_react_assets)), name="react-assets"
    )


# ========================================================================================
# Pydantic Models
# ========================================================================================


class AnalysisRequest(BaseModel):
    """Request model for analysis endpoint."""

    symbol: str = Field(..., description="Stock ticker symbol (e.g., AAPL)")
    mode: str = Field(
        default="standard",
        description="Analysis mode: quick, standard, comprehensive",
    )
    provider: str = Field(default="ollama", description="LLM provider")
    model: Optional[str] = Field(default=None, description="Model name")


class AnalysisResponse(BaseModel):
    """Response model for analysis endpoint."""

    symbol: str
    mode: str
    status: str
    fundamental_analysis: Optional[Dict[str, Any]] = None
    technical_analysis: Optional[Dict[str, Any]] = None
    market_context: Optional[Dict[str, Any]] = None
    synthesis: Optional[Dict[str, Any]] = None
    recommendation: Optional[Dict[str, Any]] = None
    errors: List[str] = []
    timestamp: str


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    version: str
    victor_installed: bool
    providers: List[str]
    services: Dict[str, str]
    timestamp: str


class BatchAnalysisRequest(BaseModel):
    """Request model for batch analysis."""

    symbols: List[str] = Field(..., description="List of stock ticker symbols")
    mode: str = Field(default="standard", description="Analysis mode")


class BatchAnalysisResponse(BaseModel):
    """Response model for batch analysis."""

    submitted: int
    job_id: str
    status: str


class CacheWarmRequest(BaseModel):
    """Request model for cache warming."""

    symbols: List[str] = Field(..., description="Symbols to warm cache for")


class UIRefreshRequest(BaseModel):
    """Request model for UI-triggered refresh."""

    mode: str = Field(
        default="comprehensive",
        description="Analysis mode: quick, standard, comprehensive",
    )
    backend: str = Field(
        default="legacy", description="Execution backend: auto, legacy, workflow"
    )
    valuation_basis: str = Field(
        default="ttm", description="Valuation basis: ttm or forward"
    )
    forward_horizon: str = Field(
        default="1y", description="Forward horizon: 1q, 2q, 3q, 1y"
    )
    force_refresh: bool = Field(
        default=True, description="Clear caches and force fresh analysis"
    )


class ModelInfo(BaseModel):
    """Model information."""

    name: str
    size: Optional[str] = None
    modified: Optional[str] = None


def _parse_analysis_mode(mode: Optional[str]) -> AnalysisMode:
    """Normalize and validate API analysis mode values."""
    normalized_mode = (mode or AnalysisMode.STANDARD.value).strip().lower()
    if not normalized_mode:
        normalized_mode = AnalysisMode.STANDARD.value

    try:
        parsed_mode = AnalysisMode(normalized_mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {mode}. Use: {', '.join(ALLOWED_API_ANALYSIS_MODES)}",
        ) from exc

    if parsed_mode not in {
        AnalysisMode.QUICK,
        AnalysisMode.STANDARD,
        AnalysisMode.COMPREHENSIVE,
    }:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid mode: {normalized_mode}. "
                f"Use: {', '.join(ALLOWED_API_ANALYSIS_MODES)}"
            ),
        )

    return parsed_mode


def _normalize_symbols(symbols: List[str]) -> List[str]:
    """Normalize symbol list for stable batch execution."""
    normalized_symbols: List[str] = []
    seen = set()

    for symbol in symbols:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol or normalized_symbol in seen:
            continue
        seen.add(normalized_symbol)
        normalized_symbols.append(normalized_symbol)

    if not normalized_symbols:
        raise HTTPException(status_code=400, detail="No valid symbols provided")

    return normalized_symbols


def _get_analysis_jobs_store() -> Dict[str, Any]:
    """Get or lazily initialize the in-memory batch job store."""
    if not hasattr(app.state, "analysis_jobs") or app.state.analysis_jobs is None:
        app.state.analysis_jobs = {}
    result: Dict[str, Any] = app.state.analysis_jobs
    return result


def _get_batch_parallelism() -> int:
    """Resolve bounded batch parallelism from environment overrides."""
    raw_value = os.getenv("VICTOR_BATCH_MAX_PARALLEL", "").strip()
    if not raw_value:
        return BATCH_ANALYSIS_MAX_PARALLEL

    try:
        parsed_value = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid VICTOR_BATCH_MAX_PARALLEL=%r. Using default %s.",
            raw_value,
            BATCH_ANALYSIS_MAX_PARALLEL,
        )
        return BATCH_ANALYSIS_MAX_PARALLEL

    return max(1, parsed_value)


def _dashboard_html_path() -> Path:
    """Return React index.html if built, else legacy dashboard.html."""
    react_index = _react_dist_dir() / "index.html"
    if react_index.exists():
        return react_index
    return Path(__file__).resolve().parent / "static" / "dashboard.html"


def _ui_cache_path(symbol: str) -> Path:
    return UI_CACHE_DIR / f"{symbol.upper()}.json"


def _is_analysis_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    schema = str(payload.get("schema_version", ""))
    if (
        schema.startswith("analysis.compact.")
        or "agents" in payload
        or "valuation" in payload
    ):
        return True
    return "summary" in payload and ("fundamental" in payload or "technical" in payload)


def _save_ui_cache(
    symbol: str, payload: Dict[str, Any], source: str, cached_at: Optional[str] = None
) -> None:
    try:
        UI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "symbol": symbol.upper(),
            "cached_at": cached_at or datetime.utcnow().isoformat(),
            "source": source,
            "payload": payload,
        }
        _ui_cache_path(symbol).write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("Failed to save UI cache for %s: %s", symbol, exc)


def _load_ui_cache(symbol: str) -> Optional[Dict[str, Any]]:
    try:
        path = _ui_cache_path(symbol)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        payload = raw.get("payload")
        if not _is_analysis_payload(payload):
            return None
        return {
            "payload": payload,
            "cached_at": raw.get("cached_at"),
            "period": raw.get("period"),
            "form_type": raw.get("form_type"),
            "source": raw.get("source", "ui_cache"),
        }
    except Exception as exc:
        logger.warning("Failed to load UI cache for %s: %s", symbol, exc)
        return None


def _extract_payload_from_log_text(raw: str, symbol: str) -> Optional[Dict[str, Any]]:
    if not raw:
        return None

    # Preferred parse from "[Full Analysis]" marker.
    marker_index = raw.rfind("[Full Analysis]")
    candidates = []
    if marker_index >= 0:
        candidates.append(raw[marker_index + len("[Full Analysis]") :])
    candidates.append(raw)

    decoder = json.JSONDecoder()
    for candidate in candidates:
        brace_match = re.search(r"\{", candidate)
        if not brace_match:
            continue
        json_candidate = candidate[brace_match.start() :].lstrip()
        try:
            parsed, _ = decoder.raw_decode(json_candidate)
        except Exception:
            continue
        if _is_analysis_payload(parsed):
            parsed_symbol = str(parsed.get("symbol", "")).upper()
            if not parsed_symbol or parsed_symbol == symbol.upper():
                result: Dict[str, Any] = parsed
                return result
    return None


def _extract_payload_from_log_file(path: Path, symbol: str) -> Optional[Dict[str, Any]]:
    try:
        if not path.exists() or not path.is_file():
            return None
        size = path.stat().st_size
        if size <= 0:
            return None

        with path.open("rb") as handle:
            if size > UI_MAX_LOG_FILE_BYTES:
                handle.seek(max(0, size - UI_MAX_LOG_FILE_BYTES))
            text_chunk = handle.read().decode("utf-8", errors="ignore")

        return _extract_payload_from_log_text(text_chunk, symbol)
    except Exception:
        return None


def _candidate_log_files(symbol: str) -> List[Path]:
    symbol_upper = symbol.upper()
    symbol_lower = symbol.lower()
    seen: set = set()
    files: List[Path] = []

    for directory in UI_LOG_SCAN_DIRS:
        if not directory.exists():
            continue
        for pattern in (f"*{symbol_upper}*.log", f"*{symbol_lower}*.log"):
            for path in directory.glob(pattern):
                key = str(path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                files.append(path)

    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return files[:UI_MAX_LOG_SCAN_FILES]


def _get_latest_payload_from_logs(symbol: str) -> Optional[Dict[str, Any]]:
    for path in _candidate_log_files(symbol):
        payload = _extract_payload_from_log_file(path, symbol)
        if payload:
            cached_at = datetime.utcfromtimestamp(path.stat().st_mtime).isoformat()
            return {
                "payload": payload,
                "cached_at": cached_at,
                "period": None,
                "form_type": None,
                "source": f"log:{path}",
            }
    return None


def _get_latest_ui_payload(symbol: str) -> Optional[Dict[str, Any]]:
    from_db = _get_latest_orchestrator_payload(symbol)
    if from_db:
        _save_ui_cache(
            symbol,
            from_db["payload"],
            source=from_db.get("source", "db"),
            cached_at=from_db.get("cached_at"),
        )
        return from_db

    from_cache = _load_ui_cache(symbol)
    if from_cache:
        return from_cache

    from_logs = _get_latest_payload_from_logs(symbol)
    if from_logs:
        _save_ui_cache(
            symbol,
            from_logs["payload"],
            source=from_logs.get("source", "log"),
            cached_at=from_logs.get("cached_at"),
        )
        return from_logs

    return None


def _normalize_valuation_inputs(
    basis: Optional[str], horizon: Optional[str]
) -> tuple[str, str]:
    normalized_basis = str(basis or "ttm").strip().lower()
    normalized_horizon = str(horizon or "1y").strip().lower()

    if normalized_basis not in {"ttm", "forward"}:
        normalized_basis = "ttm"
    if normalized_horizon not in {"1q", "2q", "3q", "1y"}:
        normalized_horizon = "1y"

    return normalized_basis, normalized_horizon


async def _run_legacy_cli_analysis(
    symbol: str,
    mode: str,
    valuation_basis: str,
    forward_horizon: str,
    force_refresh: bool,
) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    UI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    output_file = UI_CACHE_DIR / f"{symbol.upper()}_refresh_{timestamp}.json"

    cmd = [
        sys.executable,
        "cli_orchestrator.py",
        "analyze",
        symbol,
        "-m",
        mode,
        "--detail-level",
        "compact",
        "--valuation-basis",
        valuation_basis,
        "--forward-horizon",
        forward_horizon,
        "--format",
        "json",
        "--output",
        str(output_file),
    ]
    if force_refresh:
        cmd.append("--force-refresh")

    env = os.environ.copy()
    env.setdefault("INVESTIGATOR_LEGACY", "1")

    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(repo_root),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout_bytes, _ = await asyncio.wait_for(process.communicate(), timeout=20 * 60)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return {
            "returncode": 124,
            "command": cmd,
            "stdout": "Legacy CLI analysis timed out after 20 minutes.",
            "parsed_payload": None,
        }

    stdout = stdout_bytes.decode("utf-8", errors="ignore") if stdout_bytes else ""
    parsed_payload = None
    if output_file.exists():
        try:
            raw = json.loads(output_file.read_text(encoding="utf-8"))
            if _is_analysis_payload(raw):
                parsed_payload = raw
        except Exception:
            parsed_payload = None

    if parsed_payload is None:
        parsed_payload = _extract_payload_from_log_text(stdout, symbol)

    return {
        "returncode": process.returncode,
        "command": cmd,
        "stdout": stdout,
        "parsed_payload": parsed_payload,
        "output_file": str(output_file),
    }


def _coerce_json_payload(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


def _extract_basis_and_horizon_from_models(
    models: Any,
) -> tuple[Optional[str], Optional[str]]:
    basis: Optional[str] = None
    horizon: Optional[str] = None
    if not isinstance(models, dict):
        return basis, horizon

    for model in models.values():
        if not isinstance(model, dict):
            continue
        assumptions = (
            model.get("assumptions", {})
            if isinstance(model.get("assumptions"), dict)
            else {}
        )
        metadata = (
            model.get("metadata", {}) if isinstance(model.get("metadata"), dict) else {}
        )
        basis = (
            assumptions.get("valuation_basis")
            or metadata.get("valuation_basis")
            or basis
        )
        horizon = (
            assumptions.get("forward_horizon")
            or metadata.get("forward_horizon")
            or horizon
        )
        if basis and horizon:
            break

    if basis != "forward":
        horizon = None
    return basis, horizon


def _extract_forward_guidance_from_models(models: Any) -> Dict[str, Any]:
    """
    Infer forward-guidance signals from model assumptions when SEC guidance
    payload is unavailable in the compact schema.
    """
    if not isinstance(models, dict):
        return {}

    for model_name, model in models.items():
        if not isinstance(model, dict):
            continue

        assumptions = (
            model.get("assumptions", {})
            if isinstance(model.get("assumptions"), dict)
            else {}
        )
        if not assumptions:
            continue

        has_guidance = bool(assumptions.get("guidance_applied")) or any(
            str(key).startswith("guidance_") for key in assumptions
        )
        if not has_guidance:
            continue

        guidance: Dict[str, Any] = {
            "source": "valuation_model_assumptions",
            "source_model": model_name,
            "source_form": assumptions.get("guidance_source_form"),
            "confidence_score": assumptions.get("guidance_confidence_score"),
        }

        revenue_mid = assumptions.get("guidance_revenue_mid")
        if revenue_mid is not None:
            guidance["revenue_guidance"] = {
                "mid": revenue_mid,
                "horizon": assumptions.get("guidance_revenue_horizon"),
            }

        eps_mid = assumptions.get("guidance_eps_mid")
        if eps_mid is not None:
            guidance["eps_guidance"] = {
                "mid": eps_mid,
                "horizon": assumptions.get("guidance_eps_horizon"),
            }

        revenue_growth = assumptions.get("guidance_revenue_growth_used")
        if revenue_growth is None:
            revenue_growth = assumptions.get("guidance_revenue_growth_implied")
        earnings_growth = assumptions.get("guidance_earnings_growth_used")
        if earnings_growth is None:
            earnings_growth = assumptions.get("guidance_eps_growth_implied")

        if revenue_growth is not None:
            guidance["revenue_growth_guidance"] = revenue_growth
        if earnings_growth is not None:
            guidance["earnings_growth_guidance"] = earnings_growth

        return {k: v for k, v in guidance.items() if v is not None}

    return {}


def _extract_forward_guidance(sec_section: Any, models: Any) -> Dict[str, Any]:
    if isinstance(sec_section, dict):
        forward_guidance = sec_section.get("forward_guidance")
        if isinstance(forward_guidance, dict) and forward_guidance:
            return forward_guidance
    return _extract_forward_guidance_from_models(models)


def _apply_thesis_fallback(result: Dict[str, Any]) -> Dict[str, Any]:
    """Fill empty thesis with a template-based fallback using available data."""
    summary = result.get("summary", {})
    if summary.get("thesis"):
        return result
    try:
        from investigator.domain.services.template_thesis_generator import (
            generate_investment_thesis,
        )

        thesis_data = generate_investment_thesis(
            symbol=summary.get("symbol", ""),
            key_insights={},
            composite_scores={
                "overall_score": summary.get("confidence_score", 50),
                "confidence": summary.get("overall_confidence", 50),
            },
            fundamental_analysis=result.get("fundamental", {}),
        )
        summary["thesis"] = thesis_data.get("core_investment_narrative", "")
        if not summary.get("key_catalysts"):
            summary["key_catalysts"] = thesis_data.get("growth_catalysts", [])
        if not summary.get("key_risks"):
            summary["key_risks"] = thesis_data.get("bear_case_considerations", [])
    except Exception:
        pass  # Template fallback is best-effort
    return result


def _extract_ui_view_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize either compact analysis JSON or legacy orchestrator JSON into a
    stable UI payload with summary/fundamental/technical sections.
    """

    # Already normalized UI shape (cached fallback).
    if "summary" in payload and ("fundamental" in payload or "technical" in payload):
        return payload

    # Compact schema (analysis.compact.v1)
    if str(payload.get("schema_version", "")).startswith("analysis.compact."):
        price = payload.get("price", {}) or {}
        rec = payload.get("recommendation", {}) or {}
        quality = payload.get("quality", {}) or {}
        valuation = payload.get("valuation", {}) or {}
        technical = payload.get("technical", {}) or {}
        market = payload.get("market", {}) or {}
        sec = payload.get("sec", {}) or {}
        synth = payload.get("synthesis", {}) or {}

        basis = valuation.get("basis")
        horizon = valuation.get("forward_horizon")
        inferred_basis, inferred_horizon = _extract_basis_and_horizon_from_models(
            valuation.get("models", {})
        )
        if not basis:
            basis = inferred_basis
        if horizon is None:
            horizon = inferred_horizon

        forward_guidance = _extract_forward_guidance(sec, valuation.get("models", {}))
        return _apply_thesis_fallback(
            {
                "schema": "compact",
                "summary": {
                    "symbol": payload.get("symbol"),
                    "action": rec.get("action"),
                    "confidence_score": rec.get("confidence_score"),
                    "investment_grade": rec.get("investment_grade"),
                    "current_price": price.get("current"),
                    "target_price": price.get("target"),
                    "expected_return_pct": price.get("expected_return_pct"),
                    "data_quality_score": quality.get("data_quality_score"),
                    "quality_grade": quality.get("quality_grade"),
                    "valuation_basis": basis,
                    "forward_horizon": horizon,
                    "blended_fair_value": valuation.get("blended_fair_value"),
                    "overall_confidence": valuation.get("overall_confidence"),
                    "model_agreement_score": valuation.get("model_agreement_score"),
                    "dispersion_ratio": valuation.get("dispersion_ratio"),
                    "market_regime": market.get("market_regime"),
                    "sector": market.get("sector"),
                    "guidance_source_form": (
                        forward_guidance.get("source_form")
                        if isinstance(forward_guidance, dict)
                        else None
                    ),
                    "guidance_confidence_score": (
                        forward_guidance.get("confidence_score")
                        if isinstance(forward_guidance, dict)
                        else None
                    ),
                    "thesis": (
                        rec.get("executive_summary")
                        or synth.get("executive_summary")
                        or ""
                    ),
                    "key_catalysts": (
                        rec.get("key_catalysts") or synth.get("key_catalysts") or []
                    ),
                    "key_risks": (rec.get("key_risks") or synth.get("key_risks") or []),
                },
                "fundamental": {
                    "valuation": valuation,
                    "notes": payload.get("notes", []),
                    "forward_guidance": forward_guidance,
                    "sec": sec if isinstance(sec, dict) else {},
                },
                "technical": technical,
                "raw": payload,
            }
        )

    # Legacy orchestrator shape
    agents = (
        payload.get("agents", {}) if isinstance(payload.get("agents"), dict) else {}
    )
    fundamental = (
        agents.get("fundamental", {})
        if isinstance(agents.get("fundamental"), dict)
        else {}
    )
    technical = (
        agents.get("technical", {}) if isinstance(agents.get("technical"), dict) else {}
    )
    sec = agents.get("sec", {}) if isinstance(agents.get("sec"), dict) else {}

    valuation = (
        fundamental.get("valuation", {})
        if isinstance(fundamental.get("valuation"), dict)
        else {}
    )
    valuation_payload = (
        valuation.get("response", {})
        if isinstance(valuation.get("response"), dict)
        else valuation
    )
    valuation_methods = (
        valuation_payload.get("valuation_methods", {})
        if isinstance(valuation_payload.get("valuation_methods"), dict)
        else {}
    )
    basis, horizon = _extract_basis_and_horizon_from_models(valuation_methods)
    if not basis:
        basis = fundamental.get("valuation_basis")

    forward_guidance = _extract_forward_guidance(sec, valuation_methods)
    recommendation = (
        fundamental.get("recommendation")
        if isinstance(fundamental.get("recommendation"), str)
        else payload.get("recommendation")
    )
    current_price = (
        valuation_payload.get("current_price")
        if isinstance(valuation_payload, dict)
        else fundamental.get("current_price")
    )
    target_price = (
        valuation_payload.get("fair_value_estimate")
        if isinstance(valuation_payload, dict)
        else None
    )
    if target_price is None and isinstance(valuation_payload, dict):
        target_price = valuation_payload.get("fair_value")

    expected_return_pct = None
    if current_price and target_price:
        try:
            expected_return_pct = (
                (float(target_price) - float(current_price))
                / float(current_price)
                * 100.0
            )
        except Exception:
            expected_return_pct = None

    fundamental_view = dict(fundamental) if isinstance(fundamental, dict) else {}
    if isinstance(forward_guidance, dict) and forward_guidance:
        fundamental_view["forward_guidance"] = forward_guidance

    synth = (
        payload.get("synthesis", {})
        if isinstance(payload.get("synthesis"), dict)
        else {}
    )
    legacy_rec = (
        payload.get("recommendation", {})
        if isinstance(payload.get("recommendation"), dict)
        else {}
    )

    return _apply_thesis_fallback(
        {
            "schema": "legacy",
            "summary": {
                "symbol": payload.get("symbol"),
                "action": recommendation,
                "confidence_score": (
                    (fundamental.get("confidence") or {}).get("confidence_score")
                    if isinstance(fundamental.get("confidence"), dict)
                    else None
                ),
                "investment_grade": fundamental.get("investment_grade"),
                "current_price": current_price,
                "target_price": target_price,
                "expected_return_pct": expected_return_pct,
                "valuation_basis": basis or fundamental.get("fiscal_period"),
                "forward_horizon": horizon,
                "blended_fair_value": fundamental.get("fair_value"),
                "guidance_source_form": (
                    forward_guidance.get("source_form")
                    if isinstance(forward_guidance, dict)
                    else None
                ),
                "guidance_confidence_score": (
                    forward_guidance.get("confidence_score")
                    if isinstance(forward_guidance, dict)
                    else None
                ),
                "thesis": (
                    legacy_rec.get("executive_summary")
                    or synth.get("executive_summary")
                    or ""
                ),
                "key_catalysts": (
                    legacy_rec.get("key_catalysts") or synth.get("key_catalysts") or []
                ),
                "key_risks": (
                    legacy_rec.get("key_risks") or synth.get("key_risks") or []
                ),
            },
            "fundamental": fundamental_view,
            "technical": technical,
            "raw": payload,
        }
    )


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        converted = float(value)
        if not math.isfinite(converted):
            return None
        return converted
    except Exception:
        return None


def _parse_cached_at_epoch(value: Any, fallback_epoch: float) -> float:
    if isinstance(value, str) and value.strip():
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(normalized).timestamp()
        except Exception:
            return fallback_epoch
    return fallback_epoch


def _to_confidence_percent(value: Any) -> Optional[float]:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    return parsed * 100.0 if parsed <= 1.0 else parsed


def _extract_model_weight_stats(payload: Dict[str, Any]) -> Dict[str, Any]:
    valuation = payload.get("valuation", {}) if isinstance(payload, dict) else {}
    models = valuation.get("models", {}) if isinstance(valuation, dict) else {}
    if not isinstance(models, dict):
        return {
            "weighted_model_count": 0,
            "max_model_weight": None,
            "dominant_model": None,
        }

    max_weight: Optional[float] = None
    dominant_model: Optional[str] = None
    weighted_model_count = 0
    for model_name, model_payload in models.items():
        if not isinstance(model_payload, dict):
            continue
        weight = _safe_float(model_payload.get("weight"))
        if weight is None or weight <= 0:
            continue
        weighted_model_count += 1
        if max_weight is None or weight > max_weight:
            max_weight = weight
            dominant_model = str(model_name)

    return {
        "weighted_model_count": weighted_model_count,
        "max_model_weight": max_weight,
        "dominant_model": dominant_model,
    }


def _load_rankable_cache_entries() -> List[Dict[str, Any]]:
    """
    Load deduplicated latest UI cache entries (one row per symbol) suitable for ranking.
    """
    if not UI_CACHE_DIR.exists():
        return []

    latest_by_symbol: Dict[str, Dict[str, Any]] = {}
    for path in UI_CACHE_DIR.glob("*.json"):
        if not path.is_file():
            continue
        # Ignore per-run refresh snapshots and sidecar summary files.
        if "_refresh_" in path.name or path.name.endswith("_summary.json"):
            continue

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        payload = raw.get("payload") if isinstance(raw, dict) else None
        if payload is None and isinstance(raw, dict) and _is_analysis_payload(raw):
            payload = raw
        if not _is_analysis_payload(payload):
            continue

        try:
            view = _extract_ui_view_from_payload(payload)  # type: ignore[arg-type]
        except Exception:
            continue

        summary = view.get("summary", {}) if isinstance(view, dict) else {}
        symbol = (
            str(raw.get("symbol") or summary.get("symbol") or path.stem).strip().upper()
            if isinstance(raw, dict)
            else str(summary.get("symbol") or path.stem).strip().upper()
        )
        if not symbol:
            continue

        mtime_epoch = float(path.stat().st_mtime)
        cached_at = raw.get("cached_at") if isinstance(raw, dict) else None
        cached_epoch = _parse_cached_at_epoch(cached_at, mtime_epoch)
        recommendation_confidence_score = _to_confidence_percent(
            summary.get("confidence_score")
        )
        valuation_confidence_score = _to_confidence_percent(
            summary.get("overall_confidence")
        )
        confidence_score = (
            valuation_confidence_score
            if valuation_confidence_score is not None
            else recommendation_confidence_score
        )
        model_weight_stats = _extract_model_weight_stats(
            payload if isinstance(payload, dict) else {}
        )

        entry = {
            "symbol": symbol,
            "sector": str(summary.get("sector") or "Unknown"),
            "action": summary.get("action"),
            "confidence_score": confidence_score,
            "recommendation_confidence_score": recommendation_confidence_score,
            "valuation_confidence_score": valuation_confidence_score,
            "current_price": _safe_float(summary.get("current_price")),
            "target_price": _safe_float(summary.get("target_price"))
            or _safe_float(summary.get("blended_fair_value")),
            "expected_return_pct": _safe_float(summary.get("expected_return_pct")),
            "data_quality_score": _safe_float(summary.get("data_quality_score")),
            "quality_grade": summary.get("quality_grade"),
            "model_agreement_score": _safe_float(summary.get("model_agreement_score")),
            "dispersion_ratio": _safe_float(summary.get("dispersion_ratio")),
            "valuation_basis": summary.get("valuation_basis"),
            "forward_horizon": summary.get("forward_horizon"),
            "cached_at": cached_at
            or datetime.utcfromtimestamp(mtime_epoch).isoformat(),
            "cached_at_epoch": cached_epoch,
            "source": raw.get("source") if isinstance(raw, dict) else None,
            "weighted_model_count": model_weight_stats.get("weighted_model_count", 0),
            "max_model_weight": _safe_float(model_weight_stats.get("max_model_weight")),
            "dominant_model": model_weight_stats.get("dominant_model"),
        }

        current = latest_by_symbol.get(symbol)
        if current is None or float(entry["cached_at_epoch"]) >= float(
            current.get("cached_at_epoch", 0)
        ):
            latest_by_symbol[symbol] = entry

    return list(latest_by_symbol.values())


def _load_symbol_metadata(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Best-effort metadata enrichment from symbol table (beta/mktcap/sector).
    """
    if not symbols:
        return {}
    engine = getattr(getattr(app, "state", None), "db_engine", None)
    if engine is None:
        return {}

    try:
        from sqlalchemy import bindparam, text

        with engine.connect() as conn:
            col_rows = conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'symbol'
                """
                )
            ).fetchall()
            available_cols = {str(row[0]) for row in col_rows}

            select_cols = ["ticker"]
            for col in (
                "beta_12m",
                "beta",
                "beta_24m",
                "beta_36m",
                "beta_60m",
                "mktcap",
                "sec_sector",
            ):
                if col in available_cols:
                    select_cols.append(col)
            if len(select_cols) == 1:
                return {}

            query = text(
                f"SELECT {', '.join(select_cols)} FROM symbol WHERE ticker IN :symbols"
            ).bindparams(bindparam("symbols", expanding=True))
            rows = conn.execute(query, {"symbols": symbols}).mappings().all()
    except Exception:
        return {}

    metadata: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("ticker") or "").upper()
        if not symbol:
            continue
        beta = None
        for beta_col in ("beta_12m", "beta", "beta_24m", "beta_36m", "beta_60m"):
            if beta_col in row:
                candidate = _safe_float(row.get(beta_col))
                if candidate is not None:
                    beta = candidate
                    break
        metadata[symbol] = {
            "beta": beta,
            "market_cap": _safe_float(row.get("mktcap")),
            "sector": row.get("sec_sector"),
        }
    return metadata


def _compute_portfolio_preview(
    overall_longs: List[Dict[str, Any]],
    overall_shorts: List[Dict[str, Any]],
    *,
    symbol_metadata: Dict[str, Dict[str, Any]],
    portfolio_legs: int,
) -> Dict[str, Any]:
    if portfolio_legs <= 0:
        return {}

    longs = list(overall_longs[:portfolio_legs])
    shorts = list(overall_shorts[:portfolio_legs])
    if not longs or not shorts:
        return {}

    def _with_beta(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for item in items:
            symbol = str(item.get("symbol") or "").upper()
            meta = symbol_metadata.get(symbol, {})
            enriched = dict(item)
            beta = _safe_float(meta.get("beta"))
            enriched["beta_available"] = beta is not None
            enriched["beta"] = beta if beta is not None else 1.0
            out.append(enriched)
        return out

    longs = _with_beta(longs)
    shorts = _with_beta(shorts)

    def _avg(values: List[Optional[float]], default: float = 0.0) -> float:
        clean = [float(v) for v in values if v is not None]
        if not clean:
            return default
        return float(sum(clean) / len(clean))

    long_er = _avg([_safe_float(x.get("expected_return_pct")) for x in longs], 0.0)
    short_er = _avg(
        [-(_safe_float(x.get("expected_return_pct")) or 0.0) for x in shorts], 0.0
    )
    long_beta = _avg([_safe_float(x.get("beta")) for x in longs], 1.0)
    short_beta = _avg([_safe_float(x.get("beta")) for x in shorts], 1.0)

    def _sector_exposure(
        long_weight_each: float,
        short_weight_each: float,
    ) -> List[Dict[str, Any]]:
        exposure: Dict[str, float] = defaultdict(float)
        for item in longs:
            exposure[str(item.get("sector") or "Unknown")] += long_weight_each
        for item in shorts:
            exposure[str(item.get("sector") or "Unknown")] -= abs(short_weight_each)
        rows = [
            {"sector": sector, "net_exposure": round(value, 4)}
            for sector, value in exposure.items()
            if abs(value) > 1e-9
        ]
        return sorted(rows, key=lambda x: abs(x.get("net_exposure", 0)), reverse=True)

    # 50/50 gross-neutral benchmark construction.
    long_weight_eq = 0.5 / len(longs)
    short_weight_eq = -0.5 / len(shorts)
    beta_net_eq = (long_weight_eq * len(longs) * long_beta) + (
        short_weight_eq * len(shorts) * short_beta
    )
    expected_alpha_eq = 0.5 * long_er + 0.5 * short_er

    # Beta-neutral notional split.
    denom = abs(long_beta) + abs(short_beta)
    if denom <= 1e-9:
        long_notional = 0.5
        short_notional = 0.5
    else:
        long_notional = abs(short_beta) / denom
        short_notional = abs(long_beta) / denom
    long_weight_bn = long_notional / len(longs)
    short_weight_bn = -short_notional / len(shorts)
    beta_net_bn = (long_notional * long_beta) - (short_notional * short_beta)
    expected_alpha_bn = long_notional * long_er + short_notional * short_er

    beta_coverage = {
        "long_beta_available": sum(1 for x in longs if bool(x.get("beta_available"))),
        "short_beta_available": sum(1 for x in shorts if bool(x.get("beta_available"))),
    }

    return {
        "legs": {"longs": len(longs), "shorts": len(shorts)},
        "equal_weight": {
            "long_notional": 0.5,
            "short_notional": 0.5,
            "gross_exposure": 1.0,
            "net_exposure": 0.0,
            "expected_alpha_pct": round(expected_alpha_eq, 2),
            "beta_net_estimate": round(beta_net_eq, 4),
            "avg_long_beta": round(long_beta, 4),
            "avg_short_beta": round(short_beta, 4),
            "sector_balance": _sector_exposure(long_weight_eq, short_weight_eq),
        },
        "beta_neutral": {
            "long_notional": round(long_notional, 4),
            "short_notional": round(short_notional, 4),
            "gross_exposure": round(long_notional + short_notional, 4),
            "net_exposure": round(long_notional - short_notional, 4),
            "expected_alpha_pct": round(expected_alpha_bn, 2),
            "beta_net_estimate": round(beta_net_bn, 4),
            "avg_long_beta": round(long_beta, 4),
            "avg_short_beta": round(short_beta, 4),
            "sector_balance": _sector_exposure(long_weight_bn, short_weight_bn),
        },
        "beta_coverage": beta_coverage,
    }


def _build_rankings_payload(
    entries: List[Dict[str, Any]],
    *,
    limit: int,
    per_sector: int,
    min_quality: float,
    max_age_hours: float,
    min_model_agreement: float,
    max_dispersion: float,
    basis: Optional[str],
    forward_horizon: Optional[str],
    pair_limit: int = 25,
    pair_per_sector: int = 2,
    min_pair_spread: float = 5.0,
    portfolio_legs: int = 10,
    min_confidence: float = 0.0,
    require_model_agreement: bool = False,
    require_dispersion: bool = False,
    max_single_model_weight: float = 1.0,
    require_multi_model: bool = False,
    min_target_multiple: float = 0.1,
    max_target_multiple: float = 10.0,
    require_positive_target: bool = True,
    symbol_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    now_epoch = datetime.utcnow().timestamp()
    filtered: List[Dict[str, Any]] = []
    for item in entries:
        expected = _safe_float(item.get("expected_return_pct"))
        if expected is None:
            continue

        normalized_basis = str(item.get("valuation_basis") or "").strip().lower()
        normalized_horizon = str(item.get("forward_horizon") or "").strip().lower()
        if basis and normalized_basis != basis:
            continue
        if forward_horizon and normalized_horizon != forward_horizon:
            continue

        confidence_score = _safe_float(item.get("confidence_score"))
        if min_confidence > 0 and (
            confidence_score is None or confidence_score < min_confidence
        ):
            continue

        quality_score = _safe_float(item.get("data_quality_score"))
        if quality_score is not None and quality_score < min_quality:
            continue

        weighted_model_count = int(_safe_float(item.get("weighted_model_count")) or 0)
        if require_multi_model and weighted_model_count < 2:
            continue
        max_model_weight = _safe_float(item.get("max_model_weight"))
        if max_model_weight is not None and max_model_weight > max_single_model_weight:
            continue

        agreement = _safe_float(item.get("model_agreement_score"))
        if require_model_agreement and agreement is None:
            continue
        if agreement is not None and agreement < min_model_agreement:
            continue

        dispersion = _safe_float(item.get("dispersion_ratio"))
        if require_dispersion and dispersion is None:
            continue
        if dispersion is not None and dispersion > max_dispersion:
            continue

        cached_epoch = _safe_float(item.get("cached_at_epoch")) or now_epoch
        age_hours = max(0.0, (now_epoch - cached_epoch) / 3600.0)
        if age_hours > max_age_hours:
            continue

        enriched = dict(item)
        enriched["age_hours"] = round(age_hours, 2)

        current_price = _safe_float(item.get("current_price"))
        target_price = _safe_float(item.get("target_price"))
        if require_positive_target and (
            current_price is None
            or current_price <= 0
            or target_price is None
            or target_price <= 0
        ):
            continue
        if current_price is not None and current_price > 0 and target_price is not None:
            target_multiple = target_price / current_price
            if (
                target_multiple < min_target_multiple
                or target_multiple > max_target_multiple
            ):
                continue
            enriched["target_multiple"] = round(target_multiple, 4)

        filtered.append(enriched)

    symbol_metadata = symbol_metadata or {}
    long_candidates = [
        x for x in filtered if (_safe_float(x.get("expected_return_pct")) or 0.0) > 0
    ]
    short_candidates = [
        x for x in filtered if (_safe_float(x.get("expected_return_pct")) or 0.0) < 0
    ]
    overall_longs = sorted(
        long_candidates,
        key=lambda x: _safe_float(x.get("expected_return_pct")) or -9999,
        reverse=True,
    )[:limit]
    overall_shorts = sorted(
        short_candidates,
        key=lambda x: _safe_float(x.get("expected_return_pct")) or 9999,
    )[:limit]

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in filtered:
        grouped[str(item.get("sector") or "Unknown")].append(item)

    sectors: List[Dict[str, Any]] = []
    pair_candidates: List[Dict[str, Any]] = []
    for sector, items in grouped.items():
        if not items:
            continue

        sorted_longs = sorted(
            [
                x
                for x in items
                if (_safe_float(x.get("expected_return_pct")) or 0.0) > 0
            ],
            key=lambda x: _safe_float(x.get("expected_return_pct")) or -9999,
            reverse=True,
        )
        sorted_shorts = sorted(
            [
                x
                for x in items
                if (_safe_float(x.get("expected_return_pct")) or 0.0) < 0
            ],
            key=lambda x: _safe_float(x.get("expected_return_pct")) or 9999,
        )

        longs = sorted_longs[:per_sector]
        shorts = sorted_shorts[:per_sector]
        if longs and shorts:
            top_pair_spread = (
                _safe_float(longs[0].get("expected_return_pct")) or 0.0
            ) - (_safe_float(shorts[0].get("expected_return_pct")) or 0.0)
            sectors.append(
                {
                    "sector": sector,
                    "count": len(items),
                    "spread_top_pair_pct": round(top_pair_spread, 2),
                    "longs": longs,
                    "shorts": shorts,
                }
            )

        pairs_n = min(max(0, pair_per_sector), len(sorted_longs), len(sorted_shorts))
        for idx in range(pairs_n):
            long_item = sorted_longs[idx]
            short_item = sorted_shorts[idx]
            if str(long_item.get("symbol")) == str(short_item.get("symbol")):
                continue

            long_er = _safe_float(long_item.get("expected_return_pct")) or 0.0
            short_er = _safe_float(short_item.get("expected_return_pct")) or 0.0
            spread = long_er - short_er
            if spread < min_pair_spread:
                continue

            long_symbol = str(long_item.get("symbol") or "").upper()
            short_symbol = str(short_item.get("symbol") or "").upper()
            long_beta = _safe_float(
                (symbol_metadata.get(long_symbol) or {}).get("beta")
            )
            short_beta = _safe_float(
                (symbol_metadata.get(short_symbol) or {}).get("beta")
            )
            pair_candidates.append(
                {
                    "sector": sector,
                    "long": long_item,
                    "short": short_item,
                    "spread_pct": round(spread, 2),
                    "quality_floor": round(
                        min(
                            _safe_float(long_item.get("data_quality_score")) or 0.0,
                            _safe_float(short_item.get("data_quality_score")) or 0.0,
                        ),
                        1,
                    ),
                    "model_agreement_floor": round(
                        min(
                            _safe_float(long_item.get("model_agreement_score")) or 0.0,
                            _safe_float(short_item.get("model_agreement_score")) or 0.0,
                        ),
                        3,
                    ),
                    "age_ceiling_hours": round(
                        max(
                            _safe_float(long_item.get("age_hours")) or 0.0,
                            _safe_float(short_item.get("age_hours")) or 0.0,
                        ),
                        2,
                    ),
                    "long_beta": long_beta,
                    "short_beta": short_beta,
                    "beta_net_estimate": round(
                        (long_beta if long_beta is not None else 1.0)
                        - (short_beta if short_beta is not None else 1.0),
                        4,
                    ),
                }
            )

    sectors = sorted(
        sectors, key=lambda x: x.get("spread_top_pair_pct", 0), reverse=True
    )
    pairs = sorted(
        pair_candidates,
        key=lambda x: (
            x.get("spread_pct", 0),
            x.get("quality_floor", 0),
            x.get("model_agreement_floor", 0),
        ),
        reverse=True,
    )[: max(0, pair_limit)]

    portfolio_preview = _compute_portfolio_preview(
        overall_longs,
        overall_shorts,
        symbol_metadata=symbol_metadata,
        portfolio_legs=max(1, portfolio_legs),
    )

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "filters": {
            "limit": limit,
            "per_sector": per_sector,
            "min_quality": min_quality,
            "max_age_hours": max_age_hours,
            "min_model_agreement": min_model_agreement,
            "max_dispersion": max_dispersion,
            "basis": basis,
            "forward_horizon": forward_horizon,
            "pair_limit": pair_limit,
            "pair_per_sector": pair_per_sector,
            "min_pair_spread": min_pair_spread,
            "portfolio_legs": portfolio_legs,
            "min_confidence": min_confidence,
            "require_model_agreement": require_model_agreement,
            "require_dispersion": require_dispersion,
            "max_single_model_weight": max_single_model_weight,
            "require_multi_model": require_multi_model,
            "min_target_multiple": min_target_multiple,
            "max_target_multiple": max_target_multiple,
            "require_positive_target": require_positive_target,
        },
        "universe": {
            "cached_symbols": len(entries),
            "eligible_symbols": len(filtered),
            "sector_count": len({str(i.get("sector") or "Unknown") for i in filtered}),
        },
        "overall": {
            "longs": overall_longs,
            "shorts": overall_shorts,
        },
        "sectors": sectors,
        "pairs": pairs,
        "portfolio_preview": portfolio_preview,
    }


def _compute_rankings(
    *,
    limit: int,
    per_sector: int,
    min_quality: float,
    max_age_hours: float,
    min_model_agreement: float,
    max_dispersion: float,
    basis: Optional[str],
    forward_horizon: Optional[str],
    pair_limit: int,
    pair_per_sector: int,
    min_pair_spread: float,
    portfolio_legs: int,
    min_confidence: float,
    require_model_agreement: bool,
    require_dispersion: bool,
    max_single_model_weight: float,
    require_multi_model: bool,
    min_target_multiple: float,
    max_target_multiple: float,
    require_positive_target: bool,
) -> Dict[str, Any]:
    entries = _load_rankable_cache_entries()
    if not entries:
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "filters": {
                "limit": limit,
                "per_sector": per_sector,
                "min_quality": min_quality,
                "max_age_hours": max_age_hours,
                "min_model_agreement": min_model_agreement,
                "max_dispersion": max_dispersion,
                "basis": basis,
                "forward_horizon": forward_horizon,
                "pair_limit": pair_limit,
                "pair_per_sector": pair_per_sector,
                "min_pair_spread": min_pair_spread,
                "portfolio_legs": portfolio_legs,
                "min_confidence": min_confidence,
                "require_model_agreement": require_model_agreement,
                "require_dispersion": require_dispersion,
                "max_single_model_weight": max_single_model_weight,
                "require_multi_model": require_multi_model,
                "min_target_multiple": min_target_multiple,
                "max_target_multiple": max_target_multiple,
                "require_positive_target": require_positive_target,
            },
            "universe": {"cached_symbols": 0, "eligible_symbols": 0, "sector_count": 0},
            "overall": {"longs": [], "shorts": []},
            "sectors": [],
            "pairs": [],
            "portfolio_preview": {},
        }

    metadata = _load_symbol_metadata(
        [str(e.get("symbol") or "").upper() for e in entries]
    )
    return _build_rankings_payload(
        entries=entries,
        limit=limit,
        per_sector=per_sector,
        min_quality=min_quality,
        max_age_hours=max_age_hours,
        min_model_agreement=min_model_agreement,
        max_dispersion=max_dispersion,
        basis=basis,
        forward_horizon=forward_horizon,
        pair_limit=pair_limit,
        pair_per_sector=pair_per_sector,
        min_pair_spread=min_pair_spread,
        portfolio_legs=portfolio_legs,
        min_confidence=min_confidence,
        require_model_agreement=require_model_agreement,
        require_dispersion=require_dispersion,
        max_single_model_weight=max_single_model_weight,
        require_multi_model=require_multi_model,
        min_target_multiple=min_target_multiple,
        max_target_multiple=max_target_multiple,
        require_positive_target=require_positive_target,
        symbol_metadata=metadata,
    )


def _rankings_to_csv(payload: Dict[str, Any], export_type: str) -> str:
    out = io.StringIO()
    writer = csv.writer(out)

    if export_type == "overall":
        writer.writerow(
            [
                "side",
                "rank",
                "symbol",
                "sector",
                "expected_return_pct",
                "confidence_score",
                "valuation_confidence_score",
                "data_quality_score",
                "model_agreement_score",
                "dispersion_ratio",
                "weighted_model_count",
                "max_model_weight",
                "dominant_model",
                "age_hours",
                "valuation_basis",
                "forward_horizon",
                "cached_at",
            ]
        )
        for side_key in ("longs", "shorts"):
            side = "long" if side_key == "longs" else "short"
            for idx, item in enumerate(
                (payload.get("overall", {}) or {}).get(side_key, []) or [], start=1
            ):
                writer.writerow(
                    [
                        side,
                        idx,
                        item.get("symbol"),
                        item.get("sector"),
                        item.get("expected_return_pct"),
                        item.get("confidence_score"),
                        item.get("valuation_confidence_score"),
                        item.get("data_quality_score"),
                        item.get("model_agreement_score"),
                        item.get("dispersion_ratio"),
                        item.get("weighted_model_count"),
                        item.get("max_model_weight"),
                        item.get("dominant_model"),
                        item.get("age_hours"),
                        item.get("valuation_basis"),
                        item.get("forward_horizon"),
                        item.get("cached_at"),
                    ]
                )
    elif export_type == "sectors":
        writer.writerow(
            [
                "sector",
                "count",
                "spread_top_pair_pct",
                "long_candidates",
                "short_candidates",
            ]
        )
        for row in payload.get("sectors", []) or []:
            long_candidates = ", ".join(
                str(i.get("symbol")) for i in (row.get("longs") or [])
            )
            short_candidates = ", ".join(
                str(i.get("symbol")) for i in (row.get("shorts") or [])
            )
            writer.writerow(
                [
                    row.get("sector"),
                    row.get("count"),
                    row.get("spread_top_pair_pct"),
                    long_candidates,
                    short_candidates,
                ]
            )
    elif export_type == "pairs":
        writer.writerow(
            [
                "rank",
                "sector",
                "long_symbol",
                "long_expected_return_pct",
                "long_beta",
                "short_symbol",
                "short_expected_return_pct",
                "short_beta",
                "spread_pct",
                "quality_floor",
                "model_agreement_floor",
                "age_ceiling_hours",
                "beta_net_estimate",
            ]
        )
        for idx, pair in enumerate(payload.get("pairs", []) or [], start=1):
            long_item = pair.get("long") or {}
            short_item = pair.get("short") or {}
            writer.writerow(
                [
                    idx,
                    pair.get("sector"),
                    long_item.get("symbol"),
                    long_item.get("expected_return_pct"),
                    pair.get("long_beta"),
                    short_item.get("symbol"),
                    short_item.get("expected_return_pct"),
                    pair.get("short_beta"),
                    pair.get("spread_pct"),
                    pair.get("quality_floor"),
                    pair.get("model_agreement_floor"),
                    pair.get("age_ceiling_hours"),
                    pair.get("beta_net_estimate"),
                ]
            )
    else:
        # portfolio
        preview = (
            payload.get("portfolio_preview", {}) if isinstance(payload, dict) else {}
        )
        eq = (
            preview.get("equal_weight", {})
            if isinstance(preview.get("equal_weight"), dict)
            else {}
        )
        bn = (
            preview.get("beta_neutral", {})
            if isinstance(preview.get("beta_neutral"), dict)
            else {}
        )
        writer.writerow(
            [
                "portfolio_mode",
                "long_notional",
                "short_notional",
                "gross_exposure",
                "net_exposure",
            ]
        )
        writer.writerow(
            [
                "equal_weight",
                eq.get("long_notional"),
                eq.get("short_notional"),
                eq.get("gross_exposure"),
                eq.get("net_exposure"),
            ]
        )
        writer.writerow(
            [
                "beta_neutral",
                bn.get("long_notional"),
                bn.get("short_notional"),
                bn.get("gross_exposure"),
                bn.get("net_exposure"),
            ]
        )

    return out.getvalue()


def _series_to_float_list(series: Any) -> List[Optional[float]]:
    if series is None:
        return []
    values: List[Optional[float]] = []
    converter = getattr(series, "tolist", None)
    items = converter() if callable(converter) else list(series)
    for item in items:
        value = _safe_float(item)
        if value is None:
            values.append(None)
        else:
            values.append(value)
    return values


def _build_chart_payload(
    symbol: str, days: int, ui_view: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    import numpy as np
    import pandas as pd

    try:
        import pandas_ta as pta

        indicator_engine = "pandas_ta"
    except Exception as exc:
        pta = None
        indicator_engine = "native"
        logger.warning(
            "pandas_ta unavailable, using native indicator fallback for %s: %s",
            symbol,
            exc,
        )

    from investigator.config import get_config
    from investigator.infrastructure.database.market_data import get_market_data_fetcher

    fetcher = get_market_data_fetcher(get_config())
    df = fetcher.get_stock_data(symbol, days=days)
    if df is None or df.empty:
        raise HTTPException(
            status_code=404, detail=f"No market data found for {symbol}"
        )

    data = df.copy()
    for col in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["Open", "High", "Low", "Close"])
    if data.empty:
        raise HTTPException(
            status_code=404, detail=f"No valid OHLC rows found for {symbol}"
        )

    def _sma(series: pd.Series, length: int) -> pd.Series:
        return series.rolling(window=length, min_periods=length).mean()

    def _ema(series: pd.Series, length: int) -> pd.Series:
        return series.ewm(span=length, adjust=False, min_periods=length).mean()

    def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
        avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi.clip(lower=0.0, upper=100.0)

    def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        sign = np.sign(close.diff().fillna(0.0))
        return (sign * volume.fillna(0.0)).cumsum()

    data["SMA_20"] = _sma(data["Close"], 20)
    data["SMA_50"] = _sma(data["Close"], 50)
    data["SMA_100"] = _sma(data["Close"], 100)
    data["SMA_200"] = _sma(data["Close"], 200)
    data["EMA_20"] = _ema(data["Close"], 20)
    data["EMA_50"] = _ema(data["Close"], 50)
    data["EMA_100"] = _ema(data["Close"], 100)
    data["EMA_200"] = _ema(data["Close"], 200)
    data["RSI_14"] = _rsi(data["Close"], 14)

    if pta is not None:
        macd = pta.macd(data["Close"], fast=12, slow=26, signal=9)
        if macd is not None and not macd.empty:
            data = data.join(macd, how="left")
        else:
            data["MACD_12_26_9"] = None
            data["MACDs_12_26_9"] = None
            data["MACDh_12_26_9"] = None

        bbands = pta.bbands(data["Close"], length=20, std=2.0)
        if bbands is not None and not bbands.empty:
            data = data.join(bbands, how="left")

        data["OBV"] = pta.obv(data["Close"], data["Volume"])

        bb_upper_col = next(
            (col for col in data.columns if str(col).startswith("BBU_")), None
        )
        bb_middle_col = next(
            (col for col in data.columns if str(col).startswith("BBM_")), None
        )
        bb_lower_col = next(
            (col for col in data.columns if str(col).startswith("BBL_")), None
        )
    else:
        ema_fast = _ema(data["Close"], 12)
        ema_slow = _ema(data["Close"], 26)
        data["MACD_12_26_9"] = ema_fast - ema_slow
        data["MACDs_12_26_9"] = (
            data["MACD_12_26_9"].ewm(span=9, adjust=False, min_periods=9).mean()
        )
        data["MACDh_12_26_9"] = data["MACD_12_26_9"] - data["MACDs_12_26_9"]

        bb_mid = _sma(data["Close"], 20)
        bb_std = data["Close"].rolling(window=20, min_periods=20).std(ddof=0)
        data["BBU_20_2.0"] = bb_mid + (2.0 * bb_std)
        data["BBM_20_2.0"] = bb_mid
        data["BBL_20_2.0"] = bb_mid - (2.0 * bb_std)
        data["OBV"] = _obv(data["Close"], data["Volume"])
        bb_upper_col = "BBU_20_2.0"
        bb_middle_col = "BBM_20_2.0"
        bb_lower_col = "BBL_20_2.0"

    dates = [
        idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        for idx in data.index
    ]

    summary: dict[str, Any] = {}
    technical: dict[str, Any] = {}
    levels: dict[str, Any] = {}
    if isinstance(ui_view, dict):
        summary = (
            ui_view.get("summary", {})
            if isinstance(ui_view.get("summary"), dict)
            else {}
        )
        technical = (
            ui_view.get("technical", {})
            if isinstance(ui_view.get("technical"), dict)
            else {}
        )
        levels = (
            technical.get("levels", {})
            if isinstance(technical.get("levels"), dict)
            else {}
        )

    last_row = data.iloc[-1]
    current_price = _safe_float(summary.get("current_price")) or _safe_float(
        last_row.get("Close")
    )
    fair_value = _safe_float(summary.get("target_price")) or _safe_float(
        summary.get("blended_fair_value")
    )

    level_payload = {
        "pivot_point": _safe_float(levels.get("pivot_point")),
        "support_1": _safe_float(levels.get("support_1")),
        "support_2": _safe_float(levels.get("support_2")),
        "resistance_1": _safe_float(levels.get("resistance_1")),
        "resistance_2": _safe_float(levels.get("resistance_2")),
        "fair_value": fair_value,
        "current_price": current_price,
    }

    return {
        "symbol": symbol,
        "days": days,
        "rows": int(len(data)),
        "indicator_engine": indicator_engine,
        "dates": dates,
        "ohlcv": {
            "open": _series_to_float_list(data["Open"]),
            "high": _series_to_float_list(data["High"]),
            "low": _series_to_float_list(data["Low"]),
            "close": _series_to_float_list(data["Close"]),
            "volume": _series_to_float_list(data["Volume"]),
        },
        "indicators": {
            "sma_20": _series_to_float_list(data["SMA_20"]),
            "sma_50": _series_to_float_list(data["SMA_50"]),
            "sma_100": _series_to_float_list(data["SMA_100"]),
            "sma_200": _series_to_float_list(data["SMA_200"]),
            "ema_20": _series_to_float_list(data["EMA_20"]),
            "ema_50": _series_to_float_list(data["EMA_50"]),
            "ema_100": _series_to_float_list(data["EMA_100"]),
            "ema_200": _series_to_float_list(data["EMA_200"]),
            "bb_upper": _series_to_float_list(data[bb_upper_col])
            if bb_upper_col
            else [],
            "bb_middle": _series_to_float_list(data[bb_middle_col])
            if bb_middle_col
            else [],
            "bb_lower": _series_to_float_list(data[bb_lower_col])
            if bb_lower_col
            else [],
            "rsi_14": _series_to_float_list(data["RSI_14"]),
            "macd": _series_to_float_list(data.get("MACD_12_26_9")),
            "macd_signal": _series_to_float_list(data.get("MACDs_12_26_9")),
            "macd_hist": _series_to_float_list(data.get("MACDh_12_26_9")),
            "obv": _series_to_float_list(data["OBV"]),
        },
        "levels": level_payload,
    }


def _get_latest_orchestrator_payload(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch latest analysis payload from llm_responses (legacy + compact variants)."""
    try:
        if getattr(app.state, "db_engine", None) is None:
            return None

        from investigator.infrastructure.database.db import get_llm_responses_dao

        dao = get_llm_responses_dao()
        candidate_types = (
            "orchestrator_comprehensive",
            "orchestrator_standard",
            "orchestrator_quick",
            "orchestrator_compact",
            "orchestrator",
        )

        def _row_to_payload(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            if not row:
                return None
            payload = _coerce_json_payload(row.get("response"))
            if not _is_analysis_payload(payload):
                return None
            ts = row.get("ts")
            return {
                "payload": payload,
                "cached_at": ts.isoformat()
                if ts is not None and hasattr(ts, "isoformat")
                else str(ts),
                "period": row.get("period"),
                "form_type": row.get("form_type"),
                "source": f"db:{row.get('llm_type')}",
            }

        for llm_type in candidate_types:
            hit = _row_to_payload(
                dao.get_llm_response(symbol=symbol, llm_type=llm_type)
            )
            if hit:
                return hit

        # Final fallback: latest row for symbol regardless of llm_type.
        return _row_to_payload(dao.get_llm_response(symbol=symbol))
    except Exception as exc:
        logger.warning(
            "Failed to load latest orchestrator payload for %s: %s", symbol, exc
        )
        return None


# ========================================================================================
# API Endpoints
# ========================================================================================


@app.get("/ui", response_class=HTMLResponse)
async def ui_dashboard():
    """Serve lightweight research dashboard UI."""
    html_path = _dashboard_html_path()
    if not html_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"UI asset not found: {html_path}",
        )
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/ui/api/search")
async def ui_search_symbols(
    query: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Search stock symbols for UI autocomplete."""
    normalized_query = query.strip().upper()
    if not normalized_query:
        return {"query": query, "results": []}

    try:
        from sqlalchemy import text

        from investigator.infrastructure.database.symbol_repository import (
            SymbolRepository,
        )

        repo = SymbolRepository()
        sql = text(
            """
            SELECT
                ticker,
                COALESCE(description, ticker) AS description,
                COALESCE(sec_sector, 'Unknown') AS sector,
                COALESCE(sec_industry, 'Unknown') AS industry,
                mktcap
            FROM symbol
            WHERE islisted = TRUE
              AND isstock = TRUE
              AND (isetf IS NULL OR isetf = FALSE)
              AND (
                ticker ILIKE :prefix
                OR ticker ILIKE :contains
                OR COALESCE(description, '') ILIKE :contains
              )
            ORDER BY
              CASE
                WHEN ticker ILIKE :exact THEN 0
                WHEN ticker ILIKE :prefix THEN 1
                ELSE 2
              END,
              mktcap DESC NULLS LAST
            LIMIT :limit
            """
        )

        with repo.stock_engine.connect() as conn:
            rows = conn.execute(
                sql,
                {
                    "exact": normalized_query,
                    "prefix": f"{normalized_query}%",
                    "contains": f"%{normalized_query}%",
                    "limit": int(limit),
                },
            ).fetchall()

        results = [
            {
                "symbol": row[0],
                "name": row[1],
                "sector": row[2],
                "industry": row[3],
                "market_cap": float(row[4]) if row[4] is not None else None,
            }
            for row in rows
        ]
        return {"query": query, "results": results}
    except Exception as exc:
        logger.warning("UI symbol search failed for %s: %s", query, exc)
        # Fallback: local ticker map for environments without stock DB access.
        fallback_results: List[Dict[str, Any]] = []
        try:
            map_path = Path("data/sector_industry_ticker_map.txt")
            if map_path.exists():
                for raw_line in map_path.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line or "|" not in line:
                        continue
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) < 5:
                        continue
                    ticker = parts[0].upper()
                    if ticker == "TICKER":
                        continue
                    if normalized_query not in ticker:
                        continue
                    fallback_results.append(
                        {
                            "symbol": ticker,
                            "name": ticker,
                            "sector": parts[1] or parts[2] or "Unknown",
                            "industry": parts[3] or parts[4] or "Unknown",
                            "market_cap": None,
                        }
                    )
                    if len(fallback_results) >= limit:
                        break
        except Exception:
            fallback_results = []

        return {
            "query": query,
            "results": fallback_results,
            "error": str(exc),
            "source": "fallback_file" if fallback_results else "none",
        }


@app.get("/ui/api/analysis/{symbol}/latest")
async def ui_latest_analysis(symbol: str, include_raw: bool = Query(False)):
    """Get latest cached analysis for a symbol (DB, UI cache, or parsed logs)."""
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="No symbol provided")

    cached = _get_latest_ui_payload(normalized_symbol)
    if not cached:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No cached analysis found for {normalized_symbol}. Run refresh first."
            ),
        )

    payload = cached["payload"]
    view = _extract_ui_view_from_payload(payload)
    response: Dict[str, Any] = {
        "symbol": normalized_symbol,
        "cached_at": cached.get("cached_at"),
        "period": cached.get("period"),
        "form_type": cached.get("form_type"),
        "source": cached.get("source"),
        "view": view,
    }
    if include_raw:
        response["raw"] = payload
    return response


@app.get("/ui/api/chart/{symbol}")
async def ui_chart_data(symbol: str, days: int = Query(252, ge=63, le=2000)):
    """Get OHLCV + technical indicator series for dashboard charting."""
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="No symbol provided")

    ui_view = None
    cached = _get_latest_ui_payload(normalized_symbol)
    if cached:
        ui_view = _extract_ui_view_from_payload(cached.get("payload") or {})

    payload = _build_chart_payload(normalized_symbol, days, ui_view=ui_view)
    return {
        "symbol": normalized_symbol,
        "generated_at": datetime.utcnow().isoformat(),
        "chart": payload,
    }


@app.post("/ui/api/analysis/{symbol}/refresh")
async def ui_refresh_analysis(symbol: str, request: UIRefreshRequest):
    """
    Trigger fresh analysis for a symbol and return normalized UI payload.

    This keeps CLI/batch execution unchanged; UI simply calls the same workflow.
    """
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="No symbol provided")

    analysis_mode = _parse_analysis_mode(request.mode if request else None)
    backend = (
        str((request.backend if request else "legacy") or "legacy").strip().lower()
    )
    valuation_basis, forward_horizon = _normalize_valuation_inputs(
        request.valuation_basis if request else "ttm",
        request.forward_horizon if request else "1y",
    )
    force_refresh = bool(request.force_refresh) if request else True

    if backend not in {"auto", "legacy", "workflow"}:
        raise HTTPException(
            status_code=400, detail="Invalid backend. Use auto, legacy, or workflow."
        )

    workflow_error: Optional[str] = None
    legacy_error: Optional[str] = None
    live_result: Optional[Any] = None
    refresh_result_available = False

    prefer_legacy = backend == "legacy" or (
        backend == "auto" and os.getenv("INVESTIGATOR_LEGACY", "0") == "1"
    )
    if prefer_legacy:
        legacy_exec = await _run_legacy_cli_analysis(
            normalized_symbol,
            analysis_mode.value,
            valuation_basis,
            forward_horizon,
            force_refresh,
        )
        if legacy_exec["returncode"] == 0:
            if legacy_exec.get("parsed_payload"):
                parsed_payload = legacy_exec["parsed_payload"]
                _save_ui_cache(
                    normalized_symbol,
                    parsed_payload,
                    source="legacy_cli_stdout",
                    cached_at=datetime.utcnow().isoformat(),
                )
                refresh_result_available = True
                return {
                    "symbol": normalized_symbol,
                    "mode": analysis_mode.value,
                    "status": "completed",
                    "cached_at": datetime.utcnow().isoformat(),
                    "source": "legacy_cli_stdout",
                    "valuation_basis": valuation_basis,
                    "forward_horizon": forward_horizon,
                    "view": _extract_ui_view_from_payload(parsed_payload),
                }
        else:
            legacy_error = (
                legacy_exec["stdout"][-5000:]
                if legacy_exec.get("stdout")
                else "legacy CLI failed"
            )

    # If caller explicitly requested legacy refresh and it failed, don't silently serve stale cache.
    if backend == "legacy" and legacy_error and not refresh_result_available:
        logger.error(
            "UI legacy refresh failed for %s: %s", normalized_symbol, legacy_error
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "Legacy refresh failed before producing new analysis. "
                "Stale cache was not returned. "
                f"Error: {legacy_error}"
            ),
        )

    if backend == "workflow" or (backend == "auto" and not refresh_result_available):
        try:
            live_result = await run_workflow_analysis(normalized_symbol, analysis_mode)
        except Exception as exc:
            workflow_error = str(exc)

    cached = _get_latest_ui_payload(normalized_symbol)
    if cached:
        payload = cached["payload"]
        return {
            "symbol": normalized_symbol,
            "mode": analysis_mode.value,
            "status": "completed",
            "cached_at": cached.get("cached_at"),
            "source": cached.get("source"),
            "valuation_basis": valuation_basis,
            "forward_horizon": forward_horizon,
            "view": _extract_ui_view_from_payload(payload),
        }

    if live_result is not None:
        recommendation = (
            live_result.recommendation
            if isinstance(live_result.recommendation, dict)
            else {}
        )
        view = {
            "schema": "live",
            "summary": {
                "symbol": normalized_symbol,
                "action": recommendation.get("action")
                if isinstance(recommendation, dict)
                else None,
                "confidence_score": (
                    recommendation.get("confidence_score")
                    if isinstance(recommendation, dict)
                    else None
                ),
                "valuation_basis": valuation_basis,
                "thesis": (
                    recommendation.get("executive_summary", "")
                    if isinstance(recommendation, dict)
                    else ""
                ),
                "key_catalysts": (
                    recommendation.get("key_catalysts", [])
                    if isinstance(recommendation, dict)
                    else []
                ),
                "key_risks": (
                    recommendation.get("key_risks", [])
                    if isinstance(recommendation, dict)
                    else []
                ),
            },
            "fundamental": live_result.fundamental_analysis,
            "technical": live_result.technical_analysis,
        }
        _save_ui_cache(
            normalized_symbol,
            view,
            source="workflow_live",
            cached_at=datetime.utcnow().isoformat(),
        )
        return {
            "symbol": normalized_symbol,
            "mode": analysis_mode.value,
            "status": "completed",
            "cached_at": None,
            "source": "workflow_live",
            "valuation_basis": valuation_basis,
            "forward_horizon": forward_horizon,
            "view": view,
        }

    error_parts = []
    if legacy_error:
        error_parts.append(f"legacy={legacy_error}")
    if workflow_error:
        error_parts.append(f"workflow={workflow_error}")
    error_msg = (
        "; ".join(error_parts) if error_parts else "refresh failed without result"
    )
    logger.error("UI refresh failed for %s: %s", normalized_symbol, error_msg)
    raise HTTPException(status_code=500, detail=error_msg)


@app.get("/ui/api/predictions/{symbol}")
async def ui_predictions(symbol: str, limit: int = Query(50, ge=1, le=200)):
    """Get RL prediction history for a symbol."""
    normalized_symbol = symbol.strip().upper()
    try:
        from investigator.domain.services.rl.outcome_tracker import (
            ValuationOutcomesDAO,
        )

        dao = ValuationOutcomesDAO()
        records = dao.get_by_symbol(normalized_symbol, limit=limit)
        return {"symbol": normalized_symbol, "predictions": records}
    except Exception as e:
        return {
            "symbol": normalized_symbol,
            "predictions": [],
            "error": str(e),
        }


@app.get("/ui/api/history")
@app.get("/history")
async def ui_history(limit: int = Query(20, ge=1, le=200)):
    """Return recent symbols from UI cache for quick navigation."""
    items: List[Dict[str, Any]] = []
    try:
        if not UI_CACHE_DIR.exists():
            return {"items": items}

        files = sorted(
            [p for p in UI_CACHE_DIR.glob("*.json") if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]

        for path in files:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                payload = raw.get("payload") or {}
                view = _extract_ui_view_from_payload(payload)
                summary = view.get("summary", {}) if isinstance(view, dict) else {}
                items.append(
                    {
                        "symbol": raw.get("symbol")
                        or summary.get("symbol")
                        or path.stem,
                        "cached_at": raw.get("cached_at"),
                        "source": raw.get("source"),
                        "action": summary.get("action"),
                        "current_price": summary.get("current_price"),
                        "target_price": summary.get("target_price"),
                        "expected_return_pct": summary.get("expected_return_pct"),
                    }
                )
            except Exception:
                continue
    except Exception as exc:
        logger.warning("UI history load failed: %s", exc)
    return {"items": items}


@app.get("/ui/api/rankings")
async def ui_rankings(
    limit: int = Query(20, ge=1, le=100),
    per_sector: int = Query(3, ge=1, le=20),
    min_quality: float = Query(50.0, ge=0.0, le=100.0),
    max_age_hours: float = Query(24.0 * 30.0, ge=1.0, le=24.0 * 365.0),
    min_model_agreement: float = Query(0.35, ge=0.0, le=1.0),
    max_dispersion: float = Query(0.8, ge=0.0, le=10.0),
    basis: Optional[str] = Query(default=None, pattern="^(ttm|forward)$"),
    forward_horizon: Optional[str] = Query(default=None, pattern="^(1q|2q|3q|1y)$"),
    pair_limit: int = Query(25, ge=0, le=200),
    pair_per_sector: int = Query(2, ge=0, le=20),
    min_pair_spread: float = Query(5.0, ge=0.0, le=200.0),
    portfolio_legs: int = Query(10, ge=1, le=100),
    min_confidence: float = Query(40.0, ge=0.0, le=100.0),
    require_model_agreement: bool = Query(True),
    require_dispersion: bool = Query(True),
    max_single_model_weight: float = Query(0.8, ge=0.0, le=1.0),
    require_multi_model: bool = Query(True),
    min_target_multiple: float = Query(0.1, ge=0.0, le=100.0),
    max_target_multiple: float = Query(10.0, ge=0.0, le=1000.0),
    require_positive_target: bool = Query(True),
):
    """
    Rank cached symbols for long/short screening overall and per sector.

    Uses dashboard cache entries (artifacts/ui_cache/*.json), so this endpoint is
    fast and works directly with precomputed analyses.
    """
    return _compute_rankings(
        limit=limit,
        per_sector=per_sector,
        min_quality=min_quality,
        max_age_hours=max_age_hours,
        min_model_agreement=min_model_agreement,
        max_dispersion=max_dispersion,
        basis=basis,
        forward_horizon=forward_horizon,
        pair_limit=pair_limit,
        pair_per_sector=pair_per_sector,
        min_pair_spread=min_pair_spread,
        portfolio_legs=portfolio_legs,
        min_confidence=min_confidence,
        require_model_agreement=require_model_agreement,
        require_dispersion=require_dispersion,
        max_single_model_weight=max_single_model_weight,
        require_multi_model=require_multi_model,
        min_target_multiple=min_target_multiple,
        max_target_multiple=max_target_multiple,
        require_positive_target=require_positive_target,
    )


@app.get("/ui/api/rankings/export.csv", response_class=PlainTextResponse)
async def ui_rankings_export_csv(
    export_type: str = Query(
        default="overall", pattern="^(overall|sectors|pairs|portfolio)$"
    ),
    limit: int = Query(20, ge=1, le=100),
    per_sector: int = Query(3, ge=1, le=20),
    min_quality: float = Query(50.0, ge=0.0, le=100.0),
    max_age_hours: float = Query(24.0 * 30.0, ge=1.0, le=24.0 * 365.0),
    min_model_agreement: float = Query(0.35, ge=0.0, le=1.0),
    max_dispersion: float = Query(0.8, ge=0.0, le=10.0),
    basis: Optional[str] = Query(default=None, pattern="^(ttm|forward)$"),
    forward_horizon: Optional[str] = Query(default=None, pattern="^(1q|2q|3q|1y)$"),
    pair_limit: int = Query(25, ge=0, le=200),
    pair_per_sector: int = Query(2, ge=0, le=20),
    min_pair_spread: float = Query(5.0, ge=0.0, le=200.0),
    portfolio_legs: int = Query(10, ge=1, le=100),
    min_confidence: float = Query(40.0, ge=0.0, le=100.0),
    require_model_agreement: bool = Query(True),
    require_dispersion: bool = Query(True),
    max_single_model_weight: float = Query(0.8, ge=0.0, le=1.0),
    require_multi_model: bool = Query(True),
    min_target_multiple: float = Query(0.1, ge=0.0, le=100.0),
    max_target_multiple: float = Query(10.0, ge=0.0, le=1000.0),
    require_positive_target: bool = Query(True),
):
    payload = _compute_rankings(
        limit=limit,
        per_sector=per_sector,
        min_quality=min_quality,
        max_age_hours=max_age_hours,
        min_model_agreement=min_model_agreement,
        max_dispersion=max_dispersion,
        basis=basis,
        forward_horizon=forward_horizon,
        pair_limit=pair_limit,
        pair_per_sector=pair_per_sector,
        min_pair_spread=min_pair_spread,
        portfolio_legs=portfolio_legs,
        min_confidence=min_confidence,
        require_model_agreement=require_model_agreement,
        require_dispersion=require_dispersion,
        max_single_model_weight=max_single_model_weight,
        require_multi_model=require_multi_model,
        min_target_multiple=min_target_multiple,
        max_target_multiple=max_target_multiple,
        require_positive_target=require_positive_target,
    )
    csv_data = _rankings_to_csv(payload, export_type)
    filename = f"rankings_{export_type}_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return PlainTextResponse(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/ui/{path:path}", response_class=HTMLResponse)
async def ui_spa_fallback(path: str):
    """Catch-all for React client-side routing -- serves index.html."""
    html_path = _dashboard_html_path()
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="UI not available")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Victor Investment API",
        "version": VICTOR_INVEST_VERSION,
        "docs": "/docs",
        "status": "operational",
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Comprehensive health check endpoint."""
    victor_installed = Agent is not None

    # Available providers
    providers = ["ollama"]
    if victor_installed:
        providers = ["ollama", "anthropic", "openai", "groq", "deepseek"]

    # Check services
    services = {}

    # Check database
    try:
        from investigator.infrastructure.database import get_database_engine

        engine = get_database_engine()
        services["database"] = "healthy" if engine else "unavailable"
    except Exception:
        services["database"] = "unavailable"

    # Check cache
    try:
        services["cache"] = "healthy"
    except Exception:
        services["cache"] = "unavailable"

    # Check Ollama
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:11434/api/tags",
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp:
                services["ollama"] = "healthy" if resp.status == 200 else "degraded"
    except Exception:
        services["ollama"] = "unavailable"

    # Determine overall status
    overall_status = "healthy"
    if services.get("ollama") == "unavailable":
        overall_status = "degraded"
    if not victor_installed:
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        version=VICTOR_INVEST_VERSION,
        victor_installed=victor_installed,
        providers=providers,
        services=services,
        timestamp=datetime.utcnow().isoformat(),
    )


@app.post("/analyze/{symbol}", response_model=AnalysisResponse)
async def analyze_symbol(symbol: str, request: AnalysisRequest | None = None):
    """Run investment analysis on a stock symbol.

    Args:
        symbol: Stock ticker symbol (e.g., AAPL)
        request: Optional request body with analysis parameters

    Returns:
        AnalysisResponse with analysis results
    """
    if Agent is None:
        raise HTTPException(
            status_code=503,
            detail="victor-ai not installed. Install with: pip install 'victor-ai>=0.5.0,<0.6.0'",
        )

    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="No symbol provided")

    if request and request.symbol.strip().upper() != normalized_symbol:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Symbol mismatch: path symbol '{normalized_symbol}' does not match "
                f"request symbol '{request.symbol.strip().upper()}'"
            ),
        )

    # Use request params or defaults
    requested_mode = request.mode if request else AnalysisMode.STANDARD.value
    analysis_mode = _parse_analysis_mode(requested_mode)
    mode_str = analysis_mode.value

    try:
        result = await run_workflow_analysis(normalized_symbol, analysis_mode)

        # Convert to response
        return AnalysisResponse(
            symbol=normalized_symbol,
            mode=mode_str,
            status="completed",
            fundamental_analysis=result.fundamental_analysis,
            technical_analysis=result.technical_analysis,
            market_context=result.market_context,
            synthesis=result.synthesis,
            recommendation=result.recommendation,
            errors=result.errors,
            timestamp=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        logger.error(f"Analysis failed for {normalized_symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch", response_model=BatchAnalysisResponse)
async def batch_analyze(
    request: BatchAnalysisRequest,
    background_tasks: BackgroundTasks,
):
    """Submit batch analysis for multiple symbols.

    Args:
        request: Batch analysis request with list of symbols

    Returns:
        Job ID for tracking batch progress
    """
    if not request.symbols:
        raise HTTPException(status_code=400, detail="No symbols provided")

    normalized_symbols = _normalize_symbols(request.symbols)
    analysis_mode = _parse_analysis_mode(request.mode)
    mode_str = analysis_mode.value

    # Generate job ID
    job_id = f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    analysis_jobs = _get_analysis_jobs_store()

    # Store job
    analysis_jobs[job_id] = {
        "symbols": normalized_symbols,
        "mode": mode_str,
        "status": "pending",
        "results": {},
        "submitted_at": datetime.utcnow().isoformat(),
    }

    # Add background task
    background_tasks.add_task(_run_batch_analysis, job_id, normalized_symbols, mode_str)

    return BatchAnalysisResponse(
        submitted=len(normalized_symbols),
        job_id=job_id,
        status="pending",
    )


@app.get("/batch/{job_id}")
async def get_batch_status(job_id: str):
    """Get status of a batch analysis job."""
    analysis_jobs = _get_analysis_jobs_store()

    if job_id not in analysis_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = analysis_jobs[job_id]

    # Calculate progress
    total = len(job["symbols"])
    completed = len(job["results"])
    progress = completed / total if total > 0 else 0

    return {
        **job,
        "progress": progress,
        "completed_count": completed,
        "total_count": total,
    }


@app.get("/models")
async def list_models():
    """List available Ollama models."""
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:11434/api/tags") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    models = data.get("models", [])
                    return {
                        "models": [
                            {
                                "name": m.get("name"),
                                "size": m.get("size"),
                                "modified": m.get("modified_at"),
                            }
                            for m in models
                        ],
                        "count": len(models),
                    }
                else:
                    raise HTTPException(
                        status_code=resp.status, detail="Ollama unavailable"
                    )
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=503, detail=f"Cannot connect to Ollama: {e}")


@app.get("/cache/stats")
async def cache_stats():
    """Get cache statistics."""
    try:
        if app.state.cache_manager:
            stats = app.state.cache_manager.get_stats()
            return {"status": "ok", "stats": stats}
        else:
            # Try to get stats directly
            from investigator.infrastructure.cache import CacheManager

            cache = CacheManager()
            stats = cache.get_stats()
            return {"status": "ok", "stats": stats}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/cache/warm")
async def warm_cache(request: CacheWarmRequest, background_tasks: BackgroundTasks):
    """Warm cache for specified symbols."""
    try:
        if not request.symbols:
            raise HTTPException(status_code=400, detail="No symbols provided")

        # Add background task
        background_tasks.add_task(_warm_cache_for_symbols, request.symbols)

        return {
            "message": f"Cache warming started for {len(request.symbols)} symbols",
            "symbols": request.symbols,
            "status": "started",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/cache/symbol/{symbol}")
async def clear_symbol_cache(symbol: str):
    """Clear cache for a specific symbol."""
    try:
        symbol = symbol.upper()

        # Try to clear from cache manager
        if app.state.cache_manager and hasattr(app.state.cache_manager, "clear_symbol"):
            await app.state.cache_manager.clear_symbol(symbol)
        else:
            # Try direct approach
            from investigator.infrastructure.cache import CacheManager

            cache = CacheManager()
            if hasattr(cache, "clear_symbol"):
                cache.clear_symbol(symbol)

        return {
            "message": f"Cache cleared for {symbol}",
            "status": "success",
        }
    except Exception as e:
        return {
            "message": f"Cache clear attempted for {symbol}",
            "status": "partial",
            "error": str(e),
        }


# ========================================================================================
# Background Tasks
# ========================================================================================


async def _run_batch_analysis(job_id: str, symbols: List[str], mode: str):
    """Background task for batch analysis."""
    analysis_jobs = _get_analysis_jobs_store()
    job = analysis_jobs.get(job_id)
    if job is None:
        logger.error("Batch job not found: %s", job_id)
        return

    job["status"] = "running"

    try:
        try:
            analysis_mode = _parse_analysis_mode(mode)
        except HTTPException as exc:
            job["status"] = "failed"
            job["error"] = str(exc.detail)
            job["completed_at"] = datetime.utcnow().isoformat()
            return

        semaphore = asyncio.Semaphore(_get_batch_parallelism())

        async def _analyze_symbol(symbol: str):
            async with semaphore:
                try:
                    result = await run_workflow_analysis(symbol.upper(), analysis_mode)
                    return symbol, {
                        "status": "completed",
                        "recommendation": result.recommendation,
                        "errors": result.errors,
                    }
                except Exception as exc:
                    return symbol, {
                        "status": "error",
                        "error": str(exc),
                    }

        results = await asyncio.gather(*[_analyze_symbol(symbol) for symbol in symbols])
        for symbol, result_payload in results:
            job["results"][symbol] = result_payload

        error_count = sum(
            1
            for symbol_result in job["results"].values()
            if symbol_result["status"] == "error"
        )
        success_count = len(job["results"]) - error_count

        job["success_count"] = success_count
        job["error_count"] = error_count
        job["status"] = "completed" if error_count == 0 else "completed_with_errors"
        job["completed_at"] = datetime.utcnow().isoformat()

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["completed_at"] = datetime.utcnow().isoformat()


async def _warm_cache_for_symbols(symbols: List[str]):
    """Background task for cache warming."""
    try:
        from victor_invest.tools import MarketDataTool, SECFilingTool

        sec_tool = SECFilingTool()
        market_tool = MarketDataTool()

        for symbol in symbols:
            try:
                # Fetch SEC data to warm cache
                await sec_tool.execute(symbol=symbol.upper())
                # Fetch market data to warm cache
                await market_tool.execute(
                    symbol=symbol.upper(), action="get_history", days=365
                )
                logger.info(f"Cache warmed for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to warm cache for {symbol}: {e}")
    except Exception as e:
        logger.error(f"Cache warming failed: {e}")


# ========================================================================================
# Error Handlers
# ========================================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


# ========================================================================================
# Main Entry Point
# ========================================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "victor_invest.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
