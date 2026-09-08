"""Load and strictly validate Simulation validator v4.13 configuration."""

from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from .models import ArtifactSpec, CheckConfig, ComponentConfig, QuestionProfile
from .question_sources import (
    QuestionSource,
    QuestionSourceError,
    discover_question_sources,
    locate_question_artifact,
    resolve_question_source,
)


_CHECK_ID = re.compile(r"^[a-z][a-z0-9-]*\.[A-Za-z0-9_.-]+$")
_PROMPT_REF = re.compile(r"^([^:]+):L([1-9][0-9]*)(?:\s|$)")
CONTRACT_ID = "simulation.ei"
CONTRACT_SCHEMA_REVISION = 2
ACTIVE_RULESET_RELEASE = "4.13.0"
_SCORERS = {
    "ei.scheduling",
    "ei.pacing",
    "ei.simulation",
    "ei.reuse",
    "ei.effective-delivery",
}
_GAP_ZERO_BUSINESS_METRICS = {
    "Dismantled",
    "Arrive",
    "DismantledSupply",
    "ReuseConsumed",
    "total_dismantled",
    "initial_inventory",
    "totalArrive",
    "totalReuse",
}


class ConfigurationError(ValueError):
    """Raised when a v4.13 ruleset or profile is incomplete or ambiguous."""


def simulation_root() -> Path:
    return Path(__file__).resolve().parents[1]


def repository_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    for token in yaml.scan(text):
        if isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken)):
            raise ConfigurationError(f"YAML anchors and aliases are forbidden: {path}")
    payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ConfigurationError(f"YAML root must be a mapping: {path}")
    return payload


def contract_header(document_type: str) -> dict[str, Any]:
    """Return the one structural identity shared by every EI contract document."""

    return {
        "id": CONTRACT_ID,
        "schema_revision": CONTRACT_SCHEMA_REVISION,
        "document_type": document_type,
    }


def _validate_contract_header(
    payload: dict[str, Any],
    *,
    document_type: str,
    path: Path,
) -> None:
    expected = contract_header(document_type)
    if payload.get("contract") != expected:
        raise ConfigurationError(
            f"{path} must declare contract {expected!r}"
        )


def _relative_path(value: Any, *, label: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{label} must be a non-empty relative path: {path}")
    relative = PurePosixPath(value.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        raise ConfigurationError(f"{label} must not be absolute or contain '..': {path}")
    return relative.as_posix()


def _validate_region_aliases(raw: Any, *, label: str) -> dict[str, str]:
    """Validate question-local region display aliases used by adapters."""

    if not isinstance(raw, dict) or not raw:
        raise ConfigurationError(f"{label} must be a non-empty mapping")
    aliases: dict[str, str] = {}
    normalized_sources: set[str] = set()
    for source, target in raw.items():
        if not isinstance(source, str) or not source.strip():
            raise ConfigurationError(f"{label} sources must be non-empty strings")
        if not isinstance(target, str) or not target.strip():
            raise ConfigurationError(f"{label} targets must be non-empty strings")
        source_key = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", source.casefold())
        target_key = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", target.casefold())
        if not source_key or not target_key:
            raise ConfigurationError(
                f"{label} identities must contain letters, digits, or CJK characters"
            )
        if source_key in normalized_sources:
            raise ConfigurationError(
                f"{label} sources must be unique after normalization"
            )
        normalized_sources.add(source_key)
        aliases[source.strip()] = target.strip()
    return aliases


def _validate_week_axis_contract(
    raw: Any,
    *,
    label: str,
) -> dict[str, Any]:
    """Validate one declarative fixed or SitePlan-derived week axis."""

    if not isinstance(raw, dict):
        raise ConfigurationError(f"{label} must be a mapping")
    source = raw.get("source")
    expected_keys = (
        {"source", "coverage", "week_kind", "start_week", "end_week"}
        if source == "fixed"
        else {"source", "coverage", "week_kind"}
        if source == "site-plan"
        else set()
    )
    if not expected_keys:
        raise ConfigurationError(
            f"{label}.source must be fixed or site-plan"
        )
    if set(raw) != expected_keys:
        raise ConfigurationError(
            f"{label} must declare exactly {sorted(expected_keys)}"
        )
    if raw.get("coverage") not in {"exact", "contains"}:
        raise ConfigurationError(
            f"{label}.coverage must be exact or contains"
        )
    week_kind = raw.get("week_kind")
    if week_kind not in {"project", "iso"}:
        raise ConfigurationError(
            f"{label}.week_kind must be project or iso"
        )
    if source == "fixed":
        start = raw.get("start_week")
        end = raw.get("end_week")
        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in (start, end)
        ):
            raise ConfigurationError(
                f"{label} fixed start_week/end_week must be integers"
            )
        assert isinstance(start, int) and isinstance(end, int)
        if week_kind == "project":
            if start < 1 or end < start:
                raise ConfigurationError(
                    f"{label} fixed project-week range is invalid"
                )
        else:
            try:
                start_year, start_week = divmod(start, 100)
                end_year, end_week = divmod(end, 100)
                start_date = date.fromisocalendar(start_year, start_week, 1)
                end_date = date.fromisocalendar(end_year, end_week, 1)
            except ValueError as exc:
                raise ConfigurationError(
                    f"{label} fixed ISO-week range is invalid"
                ) from exc
            if end_date < start_date:
                raise ConfigurationError(
                    f"{label} fixed ISO-week range is reversed"
                )
    return dict(raw)


def _validate_seeded_drop_contract(raw: Any, *, label: str) -> dict[str, Any]:
    """Validate the prompt-owned deterministic Drop replay contract."""

    if not isinstance(raw, dict) or set(raw) != {"mode", "seed"}:
        raise ConfigurationError(
            f"{label} must declare exactly ['mode', 'seed']"
        )
    if raw.get("mode") != "seeded-random":
        raise ConfigurationError(f"{label}.mode must be seeded-random")
    seed = raw.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ConfigurationError(f"{label}.seed must be an integer")
    return dict(raw)


def load_ruleset(root: Path | None = None) -> dict[str, Any]:
    base = root or simulation_root()
    path = base / "ruleset.yaml"
    payload = _load_yaml(path)
    _validate_contract_header(payload, document_type="ruleset", path=path)
    allowed = {
        "contract",
        "release",
        "semantic_baseline",
        "description",
        "checks",
        "aggregation",
    }
    unexpected = set(payload) - allowed
    if unexpected:
        raise ConfigurationError(f"unknown ruleset fields {sorted(unexpected)}: {path}")
    if payload.get("release") != ACTIVE_RULESET_RELEASE:
        raise ConfigurationError(
            f"runtime requires ruleset release {ACTIVE_RULESET_RELEASE}: {path}"
        )
    checks = payload.get("checks")
    if (
        not isinstance(checks, list)
        or not checks
        or not all(isinstance(value, str) for value in checks)
        or len(set(checks)) != len(checks)
    ):
        raise ConfigurationError(f"ruleset checks must be a unique non-empty list: {path}")
    for check_id in checks:
        if not _CHECK_ID.fullmatch(str(check_id)):
            raise ConfigurationError(f"invalid ruleset check id {check_id!r}")
    forbidden = {"reuse-accounting.R1", "reuse-accounting.R2", "reuse-target.O2"}
    present = forbidden & set(checks)
    if present:
        raise ConfigurationError("removed checks remain registered: " + ", ".join(sorted(present)))
    if not isinstance(payload.get("aggregation"), dict):
        raise ConfigurationError(f"ruleset aggregation must be a mapping: {path}")
    return payload


def _resolve_source(
    question_id: str,
    root: Path | None = None,
    *,
    repo: Path | None = None,
    allow_legacy: bool = True,
) -> QuestionSource:
    base = (root or simulation_root()).resolve()
    repository = (repo or repository_root()).resolve()
    try:
        return resolve_question_source(
            repository,
            question_id,
            legacy_profile_root=base,
            allow_legacy=allow_legacy,
        )
    except QuestionSourceError as exc:
        raise ConfigurationError(str(exc)) from exc


def profile_path(
    question_id: str,
    root: Path | None = None,
    *,
    repo: Path | None = None,
    allow_legacy: bool = True,
) -> Path:
    return _resolve_source(
        question_id,
        root,
        repo=repo,
        allow_legacy=allow_legacy,
    ).validator_path


def load_profile(
    question_id: str,
    root: Path | None = None,
    *,
    repo: Path | None = None,
    allow_legacy: bool = True,
) -> QuestionProfile:
    base = (root or simulation_root()).resolve()
    question_source = _resolve_source(
        question_id,
        base,
        repo=repo,
        allow_legacy=allow_legacy,
    )
    path = question_source.validator_path
    payload = _load_yaml(path)
    if "full_credit_weights" in payload:
        raise ConfigurationError(
            f"full_credit_weights was removed; unsupported selected rules are inferred "
            f"from validator.yaml: {path}"
        )
    allowed_profile_keys = {
        "contract",
        "question_id",
        "ruleset_release",
        "release_status",
        "blocking_reasons",
        "artifact_roots",
        "artifacts",
        "components",
    }
    unknown_profile_keys = set(payload) - allowed_profile_keys
    if unknown_profile_keys:
        raise ConfigurationError(
            f"unknown validator.yaml fields {sorted(unknown_profile_keys)}: {path}"
        )
    _validate_contract_header(payload, document_type="question-profile", path=path)
    if payload.get("question_id") != question_id:
        raise ConfigurationError(
            f"profile question_id {payload.get('question_id')!r} does not match {question_id!r}"
        )
    ruleset = load_ruleset(base)
    ruleset_release = payload.get("ruleset_release")
    if ruleset_release != ruleset["release"]:
        raise ConfigurationError(
            f"profile ruleset_release {ruleset_release!r} does not match active "
            f"release {ruleset['release']!r}: {path}"
        )
    release_status = payload.get("release_status", "active")
    if release_status not in {"active", "question-contract-incomplete"}:
        raise ConfigurationError(f"unsupported release_status {release_status!r}: {path}")
    raw_blocking_reasons = payload.get("blocking_reasons", [])
    if not isinstance(raw_blocking_reasons, list) or not all(
        isinstance(value, str) and value.strip() for value in raw_blocking_reasons
    ):
        raise ConfigurationError(f"blocking_reasons must be non-empty strings: {path}")
    if release_status != "active" and not raw_blocking_reasons:
        raise ConfigurationError(f"blocked profile requires blocking_reasons: {path}")

    raw_roots = payload.get("artifact_roots")
    if not isinstance(raw_roots, list) or not raw_roots:
        raise ConfigurationError(f"artifact_roots must be a non-empty list: {path}")
    artifact_roots = tuple(
        _relative_path(value, label="artifact root", path=path) for value in raw_roots
    )
    if len(set(artifact_roots)) != len(artifact_roots):
        raise ConfigurationError(f"artifact_roots must be unique: {path}")

    raw_artifacts = payload.get("artifacts")
    if not isinstance(raw_artifacts, dict) or not raw_artifacts:
        raise ConfigurationError(f"artifacts must be a non-empty mapping: {path}")
    artifacts: dict[str, ArtifactSpec] = {}
    for role, raw in raw_artifacts.items():
        if not isinstance(role, str) or not role or not isinstance(raw, dict):
            raise ConfigurationError(f"invalid artifact declaration in {path}")
        unknown_artifact_keys = set(raw) - {
            "source",
            "path",
            "filenames",
            "schema",
            "required",
            "schema_options",
        }
        if unknown_artifact_keys:
            raise ConfigurationError(
                f"artifact {role!r} has unknown fields {sorted(unknown_artifact_keys)}"
            )
        source = raw.get("source")
        if source not in {"candidate", "question"}:
            raise ConfigurationError(f"artifact {role!r} source must be candidate or question")
        artifact_path = _relative_path(raw.get("path"), label=f"artifact {role}", path=path)
        raw_names = raw.get("filenames", [])
        if not isinstance(raw_names, list) or not all(
            isinstance(value, str) and value.strip() and Path(value).name == value
            for value in raw_names
        ):
            raise ConfigurationError(f"artifact {role!r} filenames must be base names")
        if source == "candidate" and not raw_names:
            raise ConfigurationError(f"candidate artifact {role!r} requires filenames")
        if source == "candidate" and Path(artifact_path).name.casefold() != raw_names[0].casefold():
            raise ConfigurationError(
                f"artifact {role!r} first filename must be the canonical Prompt filename"
            )
        if len({value.casefold() for value in raw_names}) != len(raw_names):
            raise ConfigurationError(f"artifact {role!r} filenames must be case-insensitively unique")
        schema = raw.get("schema", "generic")
        required = raw.get("required", True)
        schema_options = raw.get("schema_options", {})
        if not isinstance(schema, str) or not schema:
            raise ConfigurationError(f"artifact {role!r} requires schema")
        if not isinstance(required, bool):
            raise ConfigurationError(f"artifact {role!r} required must be boolean")
        if not isinstance(schema_options, dict):
            raise ConfigurationError(f"artifact {role!r} schema_options must be a mapping")
        if "region_aliases" in schema_options:
            schema_options = dict(schema_options)
            schema_options["region_aliases"] = _validate_region_aliases(
                schema_options["region_aliases"],
                label=f"artifact {role!r} schema_options.region_aliases",
            )
        artifacts[role] = ArtifactSpec(
            role=role,
            source=source,
            path=artifact_path,
            filenames=tuple(dict.fromkeys(raw_names)),
            schema=schema,
            required=required,
            schema_options=dict(schema_options),
        )

    ruleset_checks = set(ruleset["checks"])
    raw_components = payload.get("components")
    if not isinstance(raw_components, dict) or not raw_components:
        raise ConfigurationError(f"components must be a non-empty mapping: {path}")
    components: dict[str, ComponentConfig] = {}
    for name, raw in raw_components.items():
        if name in {"total", "reuse-target"}:
            raise ConfigurationError(f"{name!r} is not a v4.12 business component: {path}")
        if not isinstance(name, str) or not isinstance(raw, dict):
            raise ConfigurationError(f"invalid component declaration in {path}")
        unknown_component_keys = set(raw) - {"scorer", "checks", "parameters"}
        if unknown_component_keys:
            raise ConfigurationError(
                f"component {name!r} has unknown fields {sorted(unknown_component_keys)}"
            )
        scorer = raw.get("scorer")
        if scorer not in _SCORERS:
            raise ConfigurationError(f"unsupported scorer {scorer!r} for {name!r}")
        parameters = raw.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ConfigurationError(f"component {name!r} parameters must be a mapping")
        supported_s4_parameters = {"s4_missing_evidence_policy"}
        unsupported_s4_parameters = sorted(
            key
            for key in parameters
            if isinstance(key, str) and key.casefold().startswith("s4_")
            and key not in supported_s4_parameters
        )
        if unsupported_s4_parameters:
            raise ConfigurationError(
                f"component {name!r} contains unsupported S4 parameters: "
                f"{unsupported_s4_parameters}; S4 evidence is fixed to new_warehouse"
            )
        if "weight" in raw:
            raise ConfigurationError(
                f"component {name!r} weight belongs in the batch aggregation config"
            )
        raw_checks = raw.get("checks")
        if not isinstance(raw_checks, dict) or not raw_checks:
            raise ConfigurationError(f"component {name!r} checks must be a non-empty mapping")
        checks: list[CheckConfig] = []
        for local_id, check_raw in raw_checks.items():
            check_id = f"{name}.{local_id}"
            if check_id not in ruleset_checks:
                raise ConfigurationError(f"profile contains unknown check {check_id!r}: {path}")
            if not isinstance(check_raw, dict):
                raise ConfigurationError(f"check {check_id!r} must be a mapping")
            if set(check_raw) != {"prompt_refs"}:
                raise ConfigurationError(
                    f"check {check_id!r} may only declare prompt_refs"
                )
            refs = check_raw.get("prompt_refs")
            if not isinstance(refs, list) or not refs or not all(
                isinstance(value, str) and value.strip() for value in refs
            ):
                raise ConfigurationError(f"check {check_id!r} requires prompt_refs")
            checks.append(CheckConfig(check_id=check_id, prompt_refs=tuple(refs)))
        local_ids = {value.check_id.split(".", 1)[1] for value in checks}
        if scorer == "ei.effective-delivery":
            if name != "effective-delivery" or local_ids != {"O2"}:
                raise ConfigurationError(
                    "ei.effective-delivery must implement only effective-delivery.O2"
                )
            supported_o2_parameters = {
                "o2_plan_mode",
                "o2_group_by",
                "o2_delivery_action",
                "o2_site_scope",
                "o2_batch_kind",
                "o2_skip_rate",
                "o2_skip_pool_scope",
                "o2_drop_selection_contract",
                "o2_install_only_contract",
                "o2_interval_contract",
                "o2_planning_year",
                "o2_master_format",
                "o2_master_sheet_hint",
                "o2_prepared_master_plan_role",
                "o2_week_to_month",
                "o2_project_start_month",
                "o2_project_week_source",
                "o2_delivery_month_source",
                "o2_site_plan_required_fields",
                "o2_substitution_mode",
                "o2_traceability_mode",
                "o2_region_scope",
                "o2_scope_material_mode",
                "o2_final_bom_quantity_mode",
                "o2_authority_actions",
                "o2_target_curve_mode",
                "o2_monthly_capacity_mode",
                "o2_capacity_factor",
                "o2_material_source_contract",
                "o2_material_source_missing_effect",
            }
            foreign_parameters = sorted(set(parameters) - supported_o2_parameters)
            if foreign_parameters:
                raise ConfigurationError(
                    f"component {name!r} O2 contains unsupported parameters: "
                    f"{foreign_parameters}"
                )
            common_required = {
                "o2_plan_mode",
                "o2_group_by",
                "o2_delivery_action",
                "o2_site_scope",
                "o2_planning_year",
                "o2_week_to_month",
                "o2_project_week_source",
                "o2_delivery_month_source",
                "o2_site_plan_required_fields",
                "o2_substitution_mode",
                "o2_traceability_mode",
                "o2_region_scope",
                "o2_scope_material_mode",
                "o2_final_bom_quantity_mode",
            }
            missing_parameters = sorted(common_required - set(parameters))
            if missing_parameters:
                raise ConfigurationError(
                    f"component {name!r} O2 parameters are incomplete: "
                    f"{missing_parameters}"
                )
            plan_mode = parameters["o2_plan_mode"]
            if plan_mode not in {"candidate-scheduled", "fixed-authority"}:
                raise ConfigurationError(
                    f"component {name!r} O2 has invalid o2_plan_mode"
                )
            if plan_mode == "fixed-authority" and {
                "o2_monthly_capacity_mode",
                "o2_capacity_factor",
            } & set(parameters):
                raise ConfigurationError(
                    f"component {name!r} fixed-authority O2 cannot declare "
                    "candidate monthly-capacity parameters"
                )
            required_roles = {"site_plan", "scope_input", "final_material"}
            if plan_mode == "candidate-scheduled":
                candidate_required = {
                    "o2_batch_kind",
                    "o2_skip_rate",
                    "o2_skip_pool_scope",
                    "o2_interval_contract",
                    "o2_master_format",
                    "o2_master_sheet_hint",
                }
                missing_candidate = sorted(candidate_required - set(parameters))
                if missing_candidate:
                    raise ConfigurationError(
                        f"component {name!r} candidate O2 parameters are incomplete: "
                        f"{missing_candidate}"
                    )
                required_roles.update(("master_plan", "batch_input"))
            missing_roles = required_roles - set(artifacts)
            if missing_roles:
                raise ConfigurationError(
                    f"component {name!r} O2 roles are incomplete: {sorted(missing_roles)}"
                )
            expected_site_scope = (
                "fixed-site-plan"
                if plan_mode == "fixed-authority"
                else "batch_intersection"
            )
            if parameters.get("o2_site_scope") != expected_site_scope:
                raise ConfigurationError(
                    f"component {name!r} O2 {plan_mode} requires "
                    f"site_scope={expected_site_scope}"
                )
            if parameters.get("o2_group_by") != "region":
                raise ConfigurationError(
                    f"component {name!r} O2 requires group_by=region"
                )
            if parameters.get("o2_delivery_action") != "install":
                raise ConfigurationError(
                    f"component {name!r} O2 requires delivery_action=install"
                )
            authority_actions = parameters.get("o2_authority_actions")
            if authority_actions is not None and authority_actions not in (
                ["install"],
                ["install", "dismantle"],
            ):
                raise ConfigurationError(
                    f"component {name!r} O2 authority_actions must be "
                    "['install'] or ['install', 'dismantle']"
                )
            install_only_contract = parameters.get("o2_install_only_contract")
            if install_only_contract is not None:
                if (
                    not isinstance(install_only_contract, dict)
                    or set(install_only_contract) != {"forbidden_actions"}
                    or install_only_contract.get("forbidden_actions")
                    != ["dismantle"]
                ):
                    raise ConfigurationError(
                        f"component {name!r} O2 install-only contract must declare "
                        "forbidden_actions: ['dismantle']"
                    )
                if authority_actions != ["install"]:
                    raise ConfigurationError(
                        f"component {name!r} O2 install-only contract requires "
                        "o2_authority_actions=['install']"
                    )
            target_curve_mode = parameters.get(
                "o2_target_curve_mode",
                "fixed-plan"
                if plan_mode == "fixed-authority"
                else "master-distribution",
            )
            if target_curve_mode not in {
                "master-distribution",
                "completion-by-deadline",
                "fixed-plan",
            }:
                raise ConfigurationError(
                    f"component {name!r} O2 has invalid o2_target_curve_mode"
                )
            if (
                plan_mode == "fixed-authority"
                and target_curve_mode != "fixed-plan"
            ):
                raise ConfigurationError(
                    f"component {name!r} fixed-authority O2 requires "
                    "o2_target_curve_mode=fixed-plan"
                )
            if (
                plan_mode == "candidate-scheduled"
                and target_curve_mode == "fixed-plan"
            ):
                raise ConfigurationError(
                    f"component {name!r} candidate-scheduled O2 cannot use "
                    "o2_target_curve_mode=fixed-plan"
                )
            material_source_contract = parameters.get(
                "o2_material_source_contract"
            )
            material_source_missing_effect = parameters.get(
                "o2_material_source_missing_effect"
            )
            if (
                material_source_missing_effect is not None
                and material_source_missing_effect
                not in {"blocking", "diagnostic"}
            ):
                raise ConfigurationError(
                    f"component {name!r} O2 material-source missing effect must be "
                    "blocking or diagnostic"
                )
            if (
                material_source_missing_effect is not None
                and material_source_contract is None
            ):
                raise ConfigurationError(
                    f"component {name!r} O2 material-source missing effect requires "
                    "o2_material_source_contract"
                )
            if material_source_contract is not None:
                if (
                    not isinstance(material_source_contract, dict)
                    or not material_source_contract
                ):
                    raise ConfigurationError(
                        f"component {name!r} O2 material-source contract must be "
                        "a non-empty action mapping"
                    )
                invalid_source_actions = sorted(
                    set(material_source_contract) - {"install", "dismantle"}
                )
                if invalid_source_actions:
                    raise ConfigurationError(
                        f"component {name!r} O2 material-source contract has "
                        f"invalid actions: {invalid_source_actions}"
                    )
                if authority_actions is not None:
                    outside_actions = sorted(
                        set(material_source_contract) - set(authority_actions)
                    )
                    if outside_actions:
                        raise ConfigurationError(
                            f"component {name!r} O2 material-source contract "
                            f"contains unscored actions: {outside_actions}"
                        )
                for action, allowed_sources in material_source_contract.items():
                    normalized_sources = [
                        value.strip().casefold()
                        for value in allowed_sources
                        if isinstance(value, str) and value.strip()
                    ] if isinstance(allowed_sources, list) else []
                    if (
                        not isinstance(allowed_sources, list)
                        or not allowed_sources
                        or len(normalized_sources) != len(allowed_sources)
                        or len(set(normalized_sources)) != len(normalized_sources)
                    ):
                        raise ConfigurationError(
                            f"component {name!r} O2 material-source values for "
                            f"{action!r} must be non-empty normalized-unique strings"
                        )
            if (
                plan_mode == "candidate-scheduled"
                and parameters.get("o2_batch_kind") not in {"cluster", "mocn"}
            ):
                raise ConfigurationError(
                    f"component {name!r} O2 requires batch_kind cluster or mocn"
                )
            if artifacts["site_plan"].source != (
                "question" if plan_mode == "fixed-authority" else "candidate"
            ):
                raise ConfigurationError(
                    f"component {name!r} O2 {plan_mode} has invalid site_plan source"
                )
            planning_year = parameters.get("o2_planning_year")
            if not isinstance(planning_year, int) or isinstance(planning_year, bool):
                raise ConfigurationError(
                    f"component {name!r} O2 requires integer planning_year"
                )
            if plan_mode == "candidate-scheduled":
                monthly_capacity_mode = parameters.get(
                    "o2_monthly_capacity_mode"
                )
                if monthly_capacity_mode not in {
                    "hard-limit",
                    "not-applicable",
                }:
                    raise ConfigurationError(
                        f"component {name!r} candidate O2 requires explicit "
                        "o2_monthly_capacity_mode=hard-limit or not-applicable"
                    )
                skip_rate = parameters.get("o2_skip_rate")
                if (
                    isinstance(skip_rate, bool)
                    or not isinstance(skip_rate, (int, float))
                    or not math.isfinite(float(skip_rate))
                    or not 0 <= float(skip_rate) < 1
                ):
                    raise ConfigurationError(
                        f"component {name!r} O2 requires skip_rate in [0, 1)"
                    )
                capacity_factor = parameters.get("o2_capacity_factor", 1.0)
                if (
                    isinstance(capacity_factor, bool)
                    or not isinstance(capacity_factor, (int, float))
                    or not math.isfinite(float(capacity_factor))
                    or float(capacity_factor) < 0
                ):
                    raise ConfigurationError(
                        f"component {name!r} O2 requires nonnegative finite "
                        "o2_capacity_factor"
                    )
                if (
                    monthly_capacity_mode != "hard-limit"
                    and "o2_capacity_factor" in parameters
                ):
                    raise ConfigurationError(
                        f"component {name!r} O2 may declare o2_capacity_factor "
                        "only when o2_monthly_capacity_mode=hard-limit"
                    )
                skip_pool_scope = parameters.get("o2_skip_pool_scope")
                if skip_pool_scope not in {
                    "batch",
                    "region-batch",
                    "region",
                }:
                    raise ConfigurationError(
                        f"component {name!r} O2 requires o2_skip_pool_scope "
                        "batch, region-batch, or region"
                    )
                drop_selection_contract = parameters.get(
                    "o2_drop_selection_contract"
                )
                if drop_selection_contract is not None:
                    _validate_seeded_drop_contract(
                        drop_selection_contract,
                        label=(
                            f"component {name!r} O2 "
                            "o2_drop_selection_contract"
                        ),
                    )
                    if float(skip_rate) <= 0:
                        raise ConfigurationError(
                            f"component {name!r} O2 seeded Drop contract requires "
                            "a positive o2_skip_rate"
                        )
                if skip_pool_scope == "batch" and drop_selection_contract is None:
                    raise ConfigurationError(
                        f"component {name!r} O2 batch Drop scope requires "
                        "o2_drop_selection_contract"
                    )
            elif "o2_drop_selection_contract" in parameters:
                raise ConfigurationError(
                    f"component {name!r} fixed-authority O2 cannot declare "
                    "o2_drop_selection_contract"
                )
            if parameters.get("o2_week_to_month", "calendar") not in {
                "calendar",
                "four-week-project",
            }:
                raise ConfigurationError(
                    f"component {name!r} O2 has invalid week_to_month"
                )
            if (
                plan_mode == "candidate-scheduled"
                and parameters.get("o2_master_format")
                not in {
                    "standard",
                    "pip-city-wise",
                    "site-action-weekly-install",
                }
            ):
                raise ConfigurationError(
                    f"component {name!r} O2 has invalid master_format"
                )
            prepared_master_role = parameters.get("o2_prepared_master_plan_role")
            if prepared_master_role is not None:
                if (
                    not isinstance(prepared_master_role, str)
                    or not prepared_master_role.strip()
                    or prepared_master_role == "master_plan"
                ):
                    raise ConfigurationError(
                        f"component {name!r} O2 prepared-master role must be a "
                        "nonempty role distinct from master_plan"
                    )
                prepared_master = artifacts.get(prepared_master_role)
                if prepared_master is None or prepared_master.source != "candidate":
                    raise ConfigurationError(
                        f"component {name!r} O2 prepared-master role must reference "
                        "a configured candidate artifact"
                    )
            if (
                release_status == "active"
                and parameters.get("o2_master_format")
                == "site-action-weekly-install"
            ):
                master_authority = artifacts.get("master_plan")
                if master_authority is None or master_authority.source != "question":
                    raise ConfigurationError(
                        f"component {name!r} O2 site-action weekly master must use "
                        "a question-owned master_plan authority"
                    )
                if prepared_master_role is None:
                    raise ConfigurationError(
                        f"component {name!r} O2 site-action weekly master requires "
                        "o2_prepared_master_plan_role"
                    )
            if not isinstance(parameters.get("o2_master_sheet_hint", ""), str):
                raise ConfigurationError(
                    f"component {name!r} O2 master_sheet_hint must be a string"
                )
            if parameters.get("o2_project_week_source", "reconcile") not in {
                "reconcile",
                "week_num",
            }:
                raise ConfigurationError(
                    f"component {name!r} O2 has invalid project_week_source"
                )
            if parameters.get("o2_delivery_month_source") not in {
                "week-start",
                "schedule-week",
                "week-label",
            }:
                raise ConfigurationError(
                    f"component {name!r} O2 has invalid delivery_month_source"
                )
            site_plan_fields = parameters.get("o2_site_plan_required_fields")
            allowed_site_plan_fields = {
                "site_id",
                "region",
                "action",
                "project_week",
                "week_num",
                "week_label",
                "week_start",
                "status",
                "site_count",
                "cluster_id",
                "mocn_batch_id",
            }
            if (
                not isinstance(site_plan_fields, list)
                or not site_plan_fields
                or not all(
                    isinstance(value, str) and value in allowed_site_plan_fields
                    for value in site_plan_fields
                )
                or len(site_plan_fields) != len(set(site_plan_fields))
            ):
                raise ConfigurationError(
                    f"component {name!r} O2 requires a unique canonical "
                    "o2_site_plan_required_fields list"
                )
            missing_identity_fields = {
                "site_id",
                "region",
                "action",
            } - set(site_plan_fields)
            if missing_identity_fields:
                raise ConfigurationError(
                    f"component {name!r} O2 site-plan contract lacks identity "
                    f"fields: {sorted(missing_identity_fields)}"
                )
            if not {"project_week", "week_num", "week_label"} & set(
                site_plan_fields
            ):
                raise ConfigurationError(
                    f"component {name!r} O2 site-plan contract lacks a week field"
                )
            project_week_source = parameters.get("o2_project_week_source")
            if project_week_source == "week_num" and "week_num" not in site_plan_fields:
                raise ConfigurationError(
                    f"component {name!r} O2 project_week_source=week_num requires "
                    "week_num in o2_site_plan_required_fields"
                )
            delivery_month_source = parameters.get("o2_delivery_month_source")
            required_month_field = {
                "week-start": "week_start",
                "week-label": "week_label",
            }.get(delivery_month_source)
            if required_month_field and required_month_field not in site_plan_fields:
                raise ConfigurationError(
                    f"component {name!r} O2 delivery_month_source="
                    f"{delivery_month_source} requires {required_month_field} in "
                    "o2_site_plan_required_fields"
                )
            if plan_mode == "candidate-scheduled":
                contract = parameters.get("o2_interval_contract")
                if not isinstance(contract, dict):
                    raise ConfigurationError(
                        f"component {name!r} O2 requires o2_interval_contract"
                    )
                anchor = contract.get("anchor")
                if anchor not in {
                    "batch-finish",
                    "site-install",
                    "not-applicable",
                }:
                    raise ConfigurationError(
                        f"component {name!r} O2 has invalid interval anchor"
                    )
                if anchor == "not-applicable":
                    if authority_actions != ["install"]:
                        raise ConfigurationError(
                            f"component {name!r} O2 interval anchor "
                            "not-applicable requires authority_actions=['install']"
                        )
                    if set(contract) != {"anchor"}:
                        raise ConfigurationError(
                            f"component {name!r} O2 not-applicable interval "
                            "contract may only declare anchor"
                        )
                else:
                    if contract.get("relation") not in {"minimum", "exact"}:
                        raise ConfigurationError(
                            f"component {name!r} O2 has invalid interval relation"
                        )
                    lag_weeks = contract.get("lag_weeks")
                    if (
                        not isinstance(lag_weeks, int)
                        or isinstance(lag_weeks, bool)
                        or lag_weeks < 0
                    ):
                        raise ConfigurationError(
                            f"component {name!r} O2 requires nonnegative interval lag_weeks"
                        )
            mode = parameters.get("o2_substitution_mode")
            if mode not in {
                "identity-only",
                "legacy-combination",
                "legacy-target-fallback",
                "expanded-bidirectional",
                "priority-row-views",
            }:
                raise ConfigurationError(
                    f"component {name!r} O2 has invalid o2_substitution_mode"
                )
            if mode != "identity-only":
                if "substitution_source" not in artifacts:
                    raise ConfigurationError(
                        f"component {name!r} O2 substitution_source is missing"
                    )
                if artifacts["substitution_source"].source != "question":
                    raise ConfigurationError(
                        f"component {name!r} O2 substitution_source must be a "
                        "question artifact"
                    )
            if parameters.get("o2_traceability_mode") not in {
                "aggregate-feasible",
                "explicit-origin",
            }:
                raise ConfigurationError(
                    f"component {name!r} O2 has invalid o2_traceability_mode"
                )
            if parameters.get("o2_region_scope", "exact") not in {
                "exact",
                "regionless",
            }:
                raise ConfigurationError(
                    f"component {name!r} O2 has invalid o2_region_scope"
                )
            if parameters.get("o2_scope_material_mode", "raw") not in {
                "raw",
                "base-pk-standardized",
            }:
                raise ConfigurationError(
                    f"component {name!r} O2 has invalid o2_scope_material_mode"
                )
            if parameters.get("o2_final_bom_quantity_mode") not in {
                "signed-action",
                "dismantle-absolute",
                "absolute",
            }:
                raise ConfigurationError(
                    f"component {name!r} O2 has invalid o2_final_bom_quantity_mode"
                )
            if parameters.get("o2_week_to_month", "calendar") == "four-week-project":
                start_month = parameters.get("o2_project_start_month")
                if (
                    not isinstance(start_month, int)
                    or isinstance(start_month, bool)
                    or start_month < 1
                ):
                    raise ConfigurationError(
                        f"component {name!r} O2 four-week-project requires "
                        "positive o2_project_start_month"
                    )
        if scorer == "ei.scheduling" and release_status == "active":
            if parameters.get("site_scope") not in {
                "all_material_sites",
                "batch_intersection",
            }:
                raise ConfigurationError(
                    f"component {name!r} requires an explicit scheduling site_scope"
                )
            if (
                parameters["site_scope"] == "batch_intersection"
                and "batch_input" not in artifacts
            ):
                raise ConfigurationError(
                    f"component {name!r} batch_intersection requires batch_input"
                )
            if {"C5", "C6a", "C6b"} & local_ids or (
                parameters.get("drop_selection_contract") is not None
                and {"C1", "C2"} & local_ids
            ):
                if parameters.get("batch_kind") not in {"cluster", "mocn"}:
                    raise ConfigurationError(
                        f"component {name!r} requires batch_kind cluster or mocn"
                    )
                if "batch_input" not in artifacts:
                    raise ConfigurationError(
                        f"component {name!r} requires batch_input"
                    )
        if "C6a" in local_ids:
            contract = parameters.get("c6a_contract")
            if not isinstance(contract, dict):
                raise ConfigurationError(f"component {name!r} requires c6a_contract")
            if contract.get("scope", "batch") not in {"batch", "site"}:
                raise ConfigurationError(
                    f"component {name!r} has invalid c6a_contract.scope"
                )
            if contract.get("direction", "install_then_dismantle") != (
                "install_then_dismantle"
            ):
                raise ConfigurationError(
                    f"component {name!r} has invalid c6a_contract.direction"
                )
            if contract.get("relation") not in {"minimum", "exact"}:
                raise ConfigurationError(
                    f"component {name!r} has invalid c6a_contract.relation"
                )
            offset = contract.get("lag_weeks")
            if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
                raise ConfigurationError(
                    f"component {name!r} c6a_contract.lag_weeks must be a nonnegative integer"
                )
        drop_selection_contract = parameters.get("drop_selection_contract")
        drop_consumers = {"C1", "C2", "C5"} & local_ids
        if drop_selection_contract is not None and not drop_consumers:
            raise ConfigurationError(
                f"component {name!r} drop_selection_contract requires C1, C2, or C5"
            )
        if "C5" in local_ids or drop_selection_contract is not None:
            skip_pool_scope = parameters.get("skip_pool_scope")
            if skip_pool_scope not in {"batch", "region-batch", "region"}:
                raise ConfigurationError(
                    f"component {name!r} requires skip_pool_scope batch, "
                    "region-batch, or region"
                )
            if drop_selection_contract is not None:
                _validate_seeded_drop_contract(
                    drop_selection_contract,
                    label=f"component {name!r} drop_selection_contract",
                )
                skip_rate = parameters.get("skip_rate")
                if (
                    isinstance(skip_rate, bool)
                    or not isinstance(skip_rate, (int, float))
                    or not math.isfinite(float(skip_rate))
                    or not 0 < float(skip_rate) < 1
                ):
                    raise ConfigurationError(
                        f"component {name!r} seeded Drop contract requires "
                        "skip_rate in (0, 1)"
                    )
            if (
                "C5" in local_ids
                and skip_pool_scope == "batch"
                and drop_selection_contract is None
            ):
                raise ConfigurationError(
                    f"component {name!r} batch Drop scope requires "
                    "drop_selection_contract"
                )
        if "C6b" in local_ids:
            contract = parameters.get("c6b_contract")
            if not isinstance(contract, dict):
                raise ConfigurationError(f"component {name!r} requires c6b_contract")
            expected_contract = {
                "order_mode": {"numeric_ascending", "source_sequence"},
                "scope": {"region", "global"},
                "event": {"first_install_week"},
            }
            for field, allowed in expected_contract.items():
                if contract.get(field) not in allowed:
                    raise ConfigurationError(
                        f"component {name!r} has invalid c6b_contract.{field}"
                    )
        if "R3" in local_ids:
            if parameters.get("r3_validation_mode") not in {
                "CONTEXTUAL",
                "LEGACY_RESIDUAL_ONLY",
            }:
                raise ConfigurationError(
                    f"component {name!r} requires a valid r3_validation_mode"
                )
            missing_roles = {
                "final_material",
                "site_plan",
                "substitution_source",
                "scope_input",
            } - set(artifacts)
            if missing_roles:
                raise ConfigurationError(
                    f"component {name!r} R3 roles are incomplete: {sorted(missing_roles)}"
                )
        if local_ids & {"S1", "S5"} and "s1_substitution_mode" in parameters:
            if parameters.get("s1_substitution_mode") not in {
                "legacy-combination",
                "legacy-target-fallback",
                "expanded-bidirectional",
                "priority-row-views",
            }:
                raise ConfigurationError(
                    f"component {name!r} requires a valid s1_substitution_mode"
                )
            if parameters.get("s1_traceability_mode") not in {
                "aggregate-feasible",
                "explicit-origin",
            }:
                raise ConfigurationError(
                    f"component {name!r} requires a valid s1_traceability_mode"
                )
            if parameters.get("s1_region_scope", "exact") not in {"exact", "regionless"}:
                raise ConfigurationError(
                    f"component {name!r} requires a valid s1_region_scope"
                )
        if local_ids & {"S1", "S5"}:
            if parameters.get("final_bom_quantity_mode") not in {
                "signed-action",
                "dismantle-absolute",
                "absolute",
            }:
                raise ConfigurationError(
                    f"component {name!r} requires a valid final_bom_quantity_mode"
                )
        if "S1" in local_ids:
            candidate_substitution_required = parameters.get(
                "s1_candidate_substitution_required",
                True,
            )
            if not isinstance(candidate_substitution_required, bool):
                raise ConfigurationError(
                    f"component {name!r} S1 requires boolean "
                    "s1_candidate_substitution_required"
                )
            required_roles = {
                "substitution_source",
                "scope_input",
                "final_material",
            }
            if candidate_substitution_required:
                required_roles.add("material_substitution")
            missing_roles = required_roles - set(artifacts)
            if missing_roles:
                raise ConfigurationError(
                    f"component {name!r} S1 roles are incomplete: {sorted(missing_roles)}"
                )
        if "S5" in local_ids:
            if parameters.get("s5_scope_material_mode", "raw") not in {
                "raw",
                "base-pk-standardized",
            }:
                raise ConfigurationError(
                    f"component {name!r} requires a valid s5_scope_material_mode"
                )
            missing_roles = {"scope_input", "site_plan", "final_material"} - set(
                artifacts
            )
            if missing_roles:
                raise ConfigurationError(
                    f"component {name!r} S5 roles are incomplete: {sorted(missing_roles)}"
                )
        if "S6" in local_ids:
            if parameters.get("s6_time_mode", "action-week-month") not in {
                "project-week",
                "action-week-month",
            }:
                raise ConfigurationError(
                    f"component {name!r} requires a valid s6_time_mode"
                )
            week_kind = parameters.get("s6_week_kind", "project")
            if week_kind not in {"project", "iso"}:
                raise ConfigurationError(
                    f"component {name!r} requires a valid s6_week_kind"
                )
            if (
                parameters.get("s6_time_mode", "action-week-month")
                == "project-week"
                and week_kind != "project"
            ):
                raise ConfigurationError(
                    f"component {name!r} project-week mode requires project week kind"
                )
            planning_year = parameters.get("planning_year")
            if not isinstance(planning_year, int) or isinstance(planning_year, bool):
                raise ConfigurationError(
                    f"component {name!r} S6 requires integer planning_year"
                )
            require_inactive_time_blank = parameters.get(
                "s6_require_inactive_time_blank"
            )
            if not isinstance(require_inactive_time_blank, bool):
                raise ConfigurationError(
                    f"component {name!r} S6 requires boolean "
                    "s6_require_inactive_time_blank"
                )
            missing_roles = {"site_plan", "final_material"} - set(artifacts)
            if missing_roles:
                raise ConfigurationError(
                    f"component {name!r} S6 roles are incomplete: {sorted(missing_roles)}"
                )
        simulation_ids = local_ids & {"S1", "S2", "S3", "S4", "S5", "S6"}
        simulation_evidence_mode = parameters.get(
            "simulation_evidence_mode",
            "warehouse",
        )
        simulation_modes = {
            rule_id: parameters.get(
                f"{rule_id.casefold()}_evidence_mode",
                simulation_evidence_mode,
            )
            for rule_id in simulation_ids & {"S2", "S3"}
        }
        if simulation_ids and any(
            value not in {"warehouse", "gap-wide"}
            for value in simulation_modes.values()
        ):
            raise ConfigurationError(
                f"component {name!r} has an invalid rule-local simulation evidence mode"
            )
        blackout_weeks = parameters.get("blackout_weeks", 0)
        if (
            not isinstance(blackout_weeks, int)
            or isinstance(blackout_weeks, bool)
            or blackout_weeks < 0
        ):
            raise ConfigurationError(
                f"component {name!r} blackout_weeks must be a nonnegative integer"
            )
        if blackout_weeks and "S3" not in local_ids:
            raise ConfigurationError(
                f"component {name!r} positive blackout_weeks requires S3"
            )

        raw_warehouse_week_contracts = parameters.get(
            "warehouse_week_contracts"
        )
        if raw_warehouse_week_contracts is not None:
            if (
                not isinstance(raw_warehouse_week_contracts, dict)
                or not raw_warehouse_week_contracts
            ):
                raise ConfigurationError(
                    f"component {name!r} warehouse_week_contracts must be a "
                    "non-empty role mapping"
                )
            s3_roles = parameters.get("s3_required_roles", [])
            permitted_roles = (
                set(s3_roles) if "S3" in local_ids and isinstance(s3_roles, list) else set()
            )
            if "S4" in local_ids:
                permitted_roles.add("new_warehouse")
            unknown_roles = sorted(
                set(raw_warehouse_week_contracts) - permitted_roles
            )
            if unknown_roles:
                raise ConfigurationError(
                    f"component {name!r} warehouse week contracts contain "
                    f"unscored roles: {unknown_roles}"
                )
            for role, contract in raw_warehouse_week_contracts.items():
                artifact_spec = artifacts.get(role)
                if artifact_spec is None or artifact_spec.schema != "ei.warehouse":
                    raise ConfigurationError(
                        f"component {name!r} warehouse week role {role!r} "
                        "must reference an ei.warehouse artifact"
                    )
                validated_contract = _validate_week_axis_contract(
                    contract,
                    label=f"component {name!r} warehouse_week_contracts[{role!r}]",
                )
                if validated_contract["source"] == "site-plan":
                    site_plan = artifacts.get("site_plan")
                    if site_plan is None or site_plan.schema != "ei.site-plan":
                        raise ConfigurationError(
                            f"component {name!r} SitePlan-derived warehouse axis "
                            "requires an ei.site-plan site_plan artifact"
                        )

        zero_business_roles = parameters.get("warehouse_zero_business_roles")
        if zero_business_roles is not None:
            if (
                not isinstance(zero_business_roles, list)
                or not zero_business_roles
                or not all(
                    isinstance(role, str) and role.strip()
                    for role in zero_business_roles
                )
                or len(set(zero_business_roles)) != len(zero_business_roles)
            ):
                raise ConfigurationError(
                    f"component {name!r} warehouse_zero_business_roles must "
                    "be a non-empty unique role list"
                )
            if "S3" not in local_ids:
                raise ConfigurationError(
                    f"component {name!r} warehouse_zero_business_roles requires S3"
                )
            s3_roles = parameters.get("s3_required_roles", [])
            outside_s3 = sorted(set(zero_business_roles) - set(s3_roles))
            if outside_s3:
                raise ConfigurationError(
                    f"component {name!r} zero-business roles are not S3 "
                    f"warehouse roles: {outside_s3}"
                )
            missing_axis = sorted(
                set(zero_business_roles)
                - set(raw_warehouse_week_contracts or {})
            )
            if missing_axis:
                raise ConfigurationError(
                    f"component {name!r} zero-business roles require complete "
                    f"warehouse week contracts: {missing_axis}"
                )

        raw_gap_week_contract = parameters.get("gap_week_contract")
        if raw_gap_week_contract is not None:
            if not simulation_ids & {"S2", "S3", "S4"}:
                raise ConfigurationError(
                    f"component {name!r} gap_week_contract requires S2, S3, or S4"
                )
            validated_contract = _validate_week_axis_contract(
                raw_gap_week_contract,
                label=f"component {name!r} gap_week_contract",
            )
            gap_role = parameters.get("gap_role", "gap")
            gap_spec = artifacts.get(gap_role) if isinstance(gap_role, str) else None
            if gap_spec is None or gap_spec.schema != "ei.gap-wide":
                raise ConfigurationError(
                    f"component {name!r} gap_week_contract requires an "
                    "ei.gap-wide gap_role"
                )
            if validated_contract["source"] == "site-plan":
                site_plan = artifacts.get("site_plan")
                if site_plan is None or site_plan.schema != "ei.site-plan":
                    raise ConfigurationError(
                        f"component {name!r} SitePlan-derived GAP axis requires "
                        "an ei.site-plan site_plan artifact"
                    )
        zero_gap_metrics = parameters.get("gap_zero_business_metrics")
        if zero_gap_metrics is not None:
            if (
                not isinstance(zero_gap_metrics, list)
                or not zero_gap_metrics
                or not all(
                    isinstance(metric, str) and metric.strip()
                    for metric in zero_gap_metrics
                )
                or len(set(zero_gap_metrics)) != len(zero_gap_metrics)
            ):
                raise ConfigurationError(
                    f"component {name!r} gap_zero_business_metrics must be "
                    "a non-empty unique metric list"
                )
            unknown_metrics = sorted(
                set(zero_gap_metrics) - _GAP_ZERO_BUSINESS_METRICS
            )
            if unknown_metrics:
                raise ConfigurationError(
                    f"component {name!r} gap_zero_business_metrics contains "
                    f"unsupported metrics: {unknown_metrics}"
                )
            if not simulation_ids & {"S2", "S3"}:
                raise ConfigurationError(
                    f"component {name!r} gap_zero_business_metrics requires S2 or S3"
                )
            gap_role = parameters.get("gap_role", "gap")
            gap_spec = artifacts.get(gap_role) if isinstance(gap_role, str) else None
            if gap_spec is None or gap_spec.schema != "ei.gap-wide":
                raise ConfigurationError(
                    f"component {name!r} gap_zero_business_metrics requires an "
                    "ei.gap-wide gap_role"
                )
        raw_site_rollout_contract = parameters.get(
            "site_rollout_week_contract"
        )
        if raw_site_rollout_contract is not None:
            if not simulation_ids & {"S2", "S3", "S4"}:
                raise ConfigurationError(
                    f"component {name!r} site_rollout_week_contract requires "
                    "S2, S3, or S4"
                )
            validated_contract = _validate_week_axis_contract(
                raw_site_rollout_contract,
                label=f"component {name!r} site_rollout_week_contract",
            )
            if (
                validated_contract["source"] != "site-plan"
                or validated_contract["week_kind"] != "iso"
            ):
                raise ConfigurationError(
                    f"component {name!r} site_rollout_week_contract must use "
                    "a SitePlan-derived ISO week axis"
                )
            site_rollout = artifacts.get("site_rollout")
            if (
                site_rollout is None
                or site_rollout.source != "candidate"
                or site_rollout.schema != "ei.site-rollout"
                or not site_rollout.required
            ):
                raise ConfigurationError(
                    f"component {name!r} site_rollout_week_contract requires a "
                    "required candidate ei.site-rollout site_rollout artifact"
                )
            site_plan = artifacts.get("site_plan")
            if site_plan is None or site_plan.schema != "ei.site-plan":
                raise ConfigurationError(
                    f"component {name!r} SitePlan-derived rollout axis requires "
                    "an ei.site-plan site_plan artifact"
                )
        gap_wide_ids = {
            rule_id for rule_id, mode in simulation_modes.items() if mode == "gap-wide"
        }
        if gap_wide_ids:
            gap_role = parameters.get("gap_role")
            if (
                not isinstance(gap_role, str)
                or gap_role not in artifacts
                or artifacts[gap_role].schema != "ei.gap-wide"
            ):
                raise ConfigurationError(
                    f"component {name!r} gap-wide evidence requires an ei.gap-wide gap_role"
                )
            repair_weeks = parameters.get("repair_weeks")
            if (
                "S2" in gap_wide_ids
                and (
                    not isinstance(repair_weeks, int)
                    or isinstance(repair_weeks, bool)
                    or repair_weeks < 0
                )
            ):
                raise ConfigurationError(
                    f"component {name!r} gap-wide S2 requires nonnegative repair_weeks"
                )
        if "S2" in local_ids:
            repair_weeks = parameters.get("repair_weeks")
            if (
                not isinstance(repair_weeks, int)
                or isinstance(repair_weeks, bool)
                or repair_weeks < 0
            ):
                raise ConfigurationError(
                    f"component {name!r} S2 requires nonnegative repair_weeks"
                )
            reuse_rate = parameters.get("reuse_rate")
            if (
                not isinstance(reuse_rate, (int, float))
                or isinstance(reuse_rate, bool)
                or not 0 <= float(reuse_rate) <= 1
            ):
                raise ConfigurationError(
                    f"component {name!r} S2 requires reuse_rate in [0, 1]"
                )
        if "S3" in local_ids and simulation_modes.get("S3") == "warehouse":
            roles = parameters.get("s3_required_roles")
            if not isinstance(roles, list) or not roles or not all(
                isinstance(value, str) and value in artifacts for value in roles
            ):
                raise ConfigurationError(
                    f"component {name!r} S3 requires configured s3_required_roles"
                )
        if "S4" in local_ids:
            new_warehouse = artifacts.get("new_warehouse")
            if new_warehouse is None or new_warehouse.schema != "ei.warehouse":
                raise ConfigurationError(
                    f"component {name!r} S4 requires an ei.warehouse new_warehouse role"
                )
        for rule_id in ("S3", "S4", "R5"):
            policy = parameters.get(f"{rule_id.casefold()}_missing_evidence_policy")
            if policy not in {None, "full-credit"}:
                raise ConfigurationError(
                    f"component {name!r} {rule_id} has invalid missing evidence policy"
                )
        if "R5" in local_ids and "r5_zero_metrics" in parameters:
            zero_metrics = parameters.get("r5_zero_metrics")
            allowed_zero_metrics = {
                "dismantled",
                "intersitereuse",
                "reuse",
                "initialstockreuse",
            }
            if (
                not isinstance(zero_metrics, list)
                or not zero_metrics
                or any(value not in allowed_zero_metrics for value in zero_metrics)
                or len(set(zero_metrics)) != len(zero_metrics)
            ):
                raise ConfigurationError(
                    f"component {name!r} r5_zero_metrics must be a nonempty "
                    "unique list of canonical reuse quantity metrics"
                )
        if "R6" in local_ids:
            deprecated_r6_parameters = {
                "r6_contract_mode",
                "r6_metrics",
                "r6_region_policy",
                "r6_zero_denominator",
                "r6_max_abs_tolerance",
            } & set(parameters)
            if deprecated_r6_parameters:
                raise ConfigurationError(
                    f"component {name!r} contains deprecated R6 parameters: "
                    f"{sorted(deprecated_r6_parameters)}"
                )
            r6_contract = parameters.get("r6_contract", {})
            if not isinstance(r6_contract, dict):
                raise ConfigurationError(
                    f"component {name!r} r6_contract must be a mapping"
                )
            unknown_r6_contract = set(r6_contract) - {
                "coordinate_scope",
                "rate_families",
                "zero_denominator_policy",
            }
            if unknown_r6_contract:
                raise ConfigurationError(
                    f"component {name!r} r6_contract contains unsupported fields: "
                    f"{sorted(unknown_r6_contract)}"
                )
            if r6_contract.get("coordinate_scope", "item-totals") not in {
                "item-totals",
                "grand-summary-total",
            }:
                raise ConfigurationError(
                    f"component {name!r} r6_contract.coordinate_scope is invalid"
                )
            r6_families = r6_contract.get(
                "rate_families",
                ["primary", "all-scope"],
            )
            if (
                not isinstance(r6_families, list)
                or not r6_families
                or any(value not in {"primary", "all-scope"} for value in r6_families)
                or len(set(r6_families)) != len(r6_families)
            ):
                raise ConfigurationError(
                    f"component {name!r} r6_contract.rate_families must be a "
                    "nonempty unique list containing primary and/or all-scope"
                )
            if r6_contract.get(
                "zero_denominator_policy",
                "not-applicable",
            ) not in {"not-applicable", "require-blank-rate"}:
                raise ConfigurationError(
                    f"component {name!r} r6_contract.zero_denominator_policy is invalid"
                )
        components[name] = ComponentConfig(
            name=name,
            scorer=scorer,
            checks=tuple(checks),
            parameters=dict(parameters),
        )
    effective_delivery = components.get("effective-delivery")
    scheduling = components.get("scheduling")
    if (
        effective_delivery is not None
        and scheduling is not None
        and effective_delivery.parameters.get("o2_plan_mode")
        == "candidate-scheduled"
        and effective_delivery.parameters.get("o2_monthly_capacity_mode")
        == "hard-limit"
    ):
        o2_capacity_factor = float(
            effective_delivery.parameters.get("o2_capacity_factor", 1.0)
        )
        scheduling_capacity_factor = float(
            scheduling.parameters.get("capacity_factor", 1.0)
        )
        if o2_capacity_factor != scheduling_capacity_factor:
            raise ConfigurationError(
                "effective-delivery O2 and scheduling must use the same monthly "
                "capacity factor"
            )
    profile = QuestionProfile(
        question_id=question_id,
        ruleset_release=str(ruleset_release),
        artifact_roots=artifact_roots,
        artifacts=artifacts,
        components=components,
        path=path,
        release_status=release_status,
        blocking_reasons=tuple(raw_blocking_reasons),
        question_dir=question_source.directory,
        question_kind=question_source.kind,
        legacy_shared_data=question_source.uses_legacy_shared_data,
    )
    _validate_prompt_refs(profile)
    return profile


def discover_questions(
    root: Path | None = None,
    *,
    repo: Path | None = None,
    include_blocked: bool = False,
) -> tuple[str, ...]:
    base = (root or simulation_root()).resolve()
    repository = (repo or repository_root()).resolve()
    try:
        questions = tuple(
            source.question_id
            for source in discover_question_sources(
                repository,
                legacy_profile_root=base,
            )
        )
    except QuestionSourceError as exc:
        raise ConfigurationError(str(exc)) from exc
    if include_blocked:
        return questions
    return tuple(
        question
        for question in questions
        if load_profile(question, base, repo=repository).release_status == "active"
    )


def _validate_prompt_refs(profile: QuestionProfile) -> None:
    question_dir = profile.question_dir
    if question_dir is None:
        raise ConfigurationError(
            f"profile has no resolved question directory: {profile.question_id}"
        )
    question_dir = question_dir.resolve()
    line_counts: dict[Path, int] = {}
    for component in profile.components.values():
        for check in component.checks:
            for reference in check.prompt_refs:
                match = _PROMPT_REF.match(reference)
                if match is None:
                    raise ConfigurationError(
                        f"invalid Prompt locator {reference!r} for {check.check_id}"
                    )
                relative = _relative_path(
                    match.group(1),
                    label=f"Prompt locator for {check.check_id}",
                    path=profile.path,
                )
                prompt_path = (question_dir / relative).resolve()
                if not prompt_path.is_relative_to(question_dir.resolve()) or not prompt_path.is_file():
                    raise ConfigurationError(
                        f"Prompt locator file is missing for {check.check_id}: {relative}"
                    )
                if prompt_path not in line_counts:
                    line_counts[prompt_path] = len(
                        prompt_path.read_text(encoding="utf-8-sig").splitlines()
                    )
                line = int(match.group(2))
                if line > line_counts[prompt_path]:
                    raise ConfigurationError(
                        f"Prompt locator line is out of range for {check.check_id}: {reference}"
                    )


def question_contract_snapshot(
    question_id: str,
    root: Path | None = None,
    *,
    repo: Path | None = None,
    profile: QuestionProfile | None = None,
) -> dict[str, Any]:
    """Describe the question-owned sources consumed by one score."""

    base = (root or simulation_root()).resolve()
    repository = (repo or repository_root()).resolve()
    if profile is None:
        profile = load_profile(question_id, base, repo=repository)
    elif profile.question_id != question_id:
        raise ConfigurationError(
            f"profile question_id {profile.question_id!r} does not match {question_id!r}"
        )
    if profile.question_dir is None:  # pragma: no cover - load_profile guarantees this
        raise ConfigurationError(f"question source directory is missing: {question_id}")
    question_dir = profile.question_dir.resolve()
    files: dict[str, dict[str, str]] = {}
    for label, source in {
        "validator": profile.path,
        "manifest": question_dir / "manifest.json",
    }.items():
        if source.is_file():
            files[label] = {
                "path": source.relative_to(repository).as_posix(),
            }
    manifest_path = question_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        prompt = manifest.get("sources", {}).get("prompt")
        if isinstance(prompt, str):
            prompt_path = (question_dir / prompt).resolve()
            if not prompt_path.is_relative_to(question_dir):
                raise ConfigurationError(
                    f"manifest Prompt path escapes question root: {prompt}"
                )
            if prompt_path.is_file():
                files["prompt"] = {
                    "path": prompt_path.relative_to(repository).as_posix(),
                }
    question_inputs: list[dict[str, str]] = []
    for spec in profile.artifacts.values():
        if spec.source != "question":
            continue
        try:
            location = locate_question_artifact(
                repository,
                question_dir,
                question_id,
                spec.path,
                allow_legacy_shared_data=profile.legacy_shared_data,
            )
        except ValueError as exc:
            raise ConfigurationError(
                f"invalid configured question artifact for {spec.role}: {exc}"
            ) from exc
        source = location.selected_path
        if source is None:
            attempted = ", ".join(str(value) for value in location.candidates)
            raise ConfigurationError(
                f"configured question artifact is missing for {spec.role}; tried: {attempted}"
            )
        question_inputs.append(
            {
                "role": spec.role,
                "path": source.relative_to(repository).as_posix(),
            }
        )
    return {
        "contract": contract_header("question-contract-snapshot"),
        "question_id": question_id,
        "question_kind": profile.question_kind,
        "question_root": question_dir.relative_to(repository).as_posix(),
        "files": files,
        "question_inputs": sorted(question_inputs, key=lambda value: value["role"]),
    }
