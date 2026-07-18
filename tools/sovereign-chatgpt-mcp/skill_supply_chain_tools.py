from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
from typing import Any, Callable, Final
import zipfile

from mcp.types import ToolAnnotations

from policy import safe_repo_path


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

_MAX_ARCHIVE_BYTES: Final[int] = 25 * 1024 * 1024
_MAX_UNCOMPRESSED_BYTES: Final[int] = 64 * 1024 * 1024
_MAX_MEMBERS: Final[int] = 5_000
_MAX_MEMBER_BYTES: Final[int] = 4 * 1024 * 1024
_MAX_TEXT_BYTES: Final[int] = 700_000
_MAX_FINDINGS: Final[int] = 180
_MAX_CATALOG_ITEMS: Final[int] = 2_000
_MAX_PDF_BYTES: Final[int] = 33 * 1024 * 1024
_PROGRESS_SCALE: Final[int] = 1_000

_TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".json",
    ".jsonl", ".yaml", ".yml", ".toml", ".xml", ".sql", ".sh", ".bash",
    ".css", ".scss", ".html", ".typ", ".java", ".kt", ".go", ".rs",
}
_SCRIPT_SUFFIXES = {".py", ".js", ".ts", ".sh", ".bash", ".ps1", ".bat", ".cmd"}
_BINARY_SUFFIXES = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".class", ".jar", ".apk", ".aab",
    ".pyc", ".pyo", ".wasm", ".node",
}
_SECRET_MARKER = re.compile(
    r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|github_pat_[A-Za-z0-9_]+|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----|"
    r"Authorization\s*:\s*(?:Bearer\s+)?\S+)",
    re.I,
)
_URL = re.compile(r"https?://[^\s<>'\")\]]+", re.I)
_ABSOLUTE_PATH = re.compile(r"(?:^|[\s'\"`])/(?:home|opt|etc|root|var|usr|tmp|run)/[^\s'\"`]+", re.M)
_NETWORK_CODE = re.compile(r"\b(?:requests\.|urllib\.|httpx\.|fetch\(|axios\.|gh\s+api|curl\s|wget\s)", re.I)
_SHELL_CODE = re.compile(r"\b(?:subprocess\.|os\.system\(|shell\s*=\s*True|Popen\(|child_process|exec\s+)", re.I)
_INSTALL_CODE = re.compile(r"\b(?:pip3?|npm|pnpm|yarn|apt(?:-get)?|dnf|yum|cargo)\s+(?:install|add)\b", re.I)
_ENV_ACCESS = re.compile(r"\b(?:os\.environ|os\.getenv|process\.env|GITHUB_TOKEN|API_KEY|SECRET)\b", re.I)
_FILE_WRITE = re.compile(r"\b(?:write_text\(|write_bytes\(|open\([^\n]{0,120}['\"]w|mkdir\(|makedirs\(|unlink\(|rmtree\(|chmod\()", re.I)
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z][A-Za-z0-9_]*)\s*\}\}")
_SAFE_ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_SAFE_DOMAIN = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

_RUNTIME: Any = None
_REGISTERED = False


SOURCE_PROFILES: Final[dict[str, dict[str, Any]]] = {
    "goal-tracker": {
        "kind": "executable_core",
        "priority": "very_high",
        "disposition": "rewrite_as_evidence_bound_goal_runtime",
        "tools": [
            "goal_runtime_schema_plan", "goal_progress_projection", "goal_transition_preview",
            "goal_reconcile_runtime_plan",
        ],
    },
    "typst-pdf-maker": {
        "kind": "executable_core",
        "priority": "very_high",
        "disposition": "split_into_bounded_document_planning_and_artifact_verification",
        "tools": ["document_plan", "typst_document_prepare_plan", "pdf_artifact_verify"],
    },
    "skill-creator": {
        "kind": "executable_core",
        "priority": "very_high",
        "disposition": "use_as_non_executing_skill_supply_chain",
        "tools": ["skill_archive_inspect", "skill_validate", "skill_capability_extract", "skill_tool_contract_preview"],
    },
    "internet-skill-finder": {
        "kind": "external_discovery",
        "priority": "high",
        "disposition": "local_cache_first_exact_revision_only",
        "tools": ["skill_catalog_search", "skill_candidate_compare"],
    },
    "github-gem-seeker": {
        "kind": "external_discovery",
        "priority": "high",
        "disposition": "evaluate_only_no_host_install",
        "tools": ["github_solution_evaluate", "github_solution_integration_plan"],
    },
    "android-industrial-ui-design": {
        "kind": "workflow_knowledge",
        "priority": "medium_high",
        "disposition": "convert_guidelines_to_static_contract_audits",
        "tools": ["android_ui_contract_audit", "android_ui_surface_map"],
    },
    "similarweb-analytics": {
        "kind": "provider_concept",
        "priority": "medium",
        "disposition": "provider_status_and_query_plan_until_protected_client_exists",
        "tools": ["domain_analytics_capability_status", "domain_analytics_query_plan"],
    },
    "alternative-blog-writer": {
        "kind": "workflow_knowledge",
        "priority": "medium",
        "disposition": "separate_research_evidence_writer_and_claim_audit",
        "tools": ["content_research_plan", "content_source_ledger_audit", "content_claim_audit"],
    },
    "listicle-blog-writer": {
        "kind": "workflow_knowledge",
        "priority": "medium",
        "disposition": "separate_research_evidence_writer_and_claim_audit",
        "tools": ["content_research_plan", "content_source_ledger_audit", "content_claim_audit"],
    },
    "nocode-llm-template-forge": {
        "kind": "weak_executable_core",
        "priority": "high",
        "disposition": "replace_free_path_markdown_copy_with_curated_template_contracts",
        "tools": [
            "template_catalog_list", "template_contract_audit", "template_generation_plan",
            "template_candidate_save_preview", "template_project_structure_analyze",
        ],
    },
}


CURATED_TEMPLATES: Final[dict[str, dict[str, Any]]] = {
    "react-typescript-surface": {
        "category": "web_project",
        "description": "Bounded React/TypeScript surface plan using the repository's existing package and design contracts.",
        "required": ["project_name"],
        "optional": {"route_prefix": "/", "design_system": "existing-sovereign", "include_api_client": False},
        "forbidden": ["package_install_command", "api_key", "absolute_output_path"],
        "files": ["README.md", "project.manifest.json", "src/App.tsx"],
    },
    "postgres-vector-schema": {
        "category": "database_schema",
        "description": "PostgreSQL/pgvector schema proposal with explicit dimension, metric and migration evidence gates.",
        "required": ["collection_name", "dimension"],
        "optional": {"metric": "cosine", "metadata_fields": ["source", "category", "created_at"]},
        "forbidden": ["connection_string", "database_password", "free_sql"],
        "files": ["README.md", "schema.contract.json", "migration.preview.sql"],
    },
    "android-operator-surface": {
        "category": "android_ui",
        "description": "Android-first operator surface using existing components, 48dp targets and evidence-aware status states.",
        "required": ["surface_name"],
        "optional": {"minimum_touch_dp": 48, "status_modes": ["ready", "blocked", "running", "failed"]},
        "forbidden": ["new_app_root", "desktop_only_hover", "color_only_status"],
        "files": ["README.md", "ui.contract.json", "OperatorSurface.tsx"],
    },
    "python-bounded-worker": {
        "category": "script",
        "description": "Pure Python worker scaffold with JSON input/output and no shell or network access by default.",
        "required": ["worker_name"],
        "optional": {"timeout_seconds": 30, "network_access": False, "writes_files": False},
        "forbidden": ["shell_command", "secret", "host_path"],
        "files": ["README.md", "worker.contract.json", "worker.py"],
    },
    "content-evidence-pipeline": {
        "category": "content_workflow",
        "description": "Research, source ledger, claim audit and artifact export workflow without mixed truth claims.",
        "required": ["topic", "audience"],
        "optional": {"output": "markdown", "requires_price_date": True, "requires_homepage_capture": False},
        "forbidden": ["fabricated_reviews", "unverified_superlatives"],
        "files": ["README.md", "research.plan.json", "source-ledger.schema.json"],
    },
}

_ALLOWED_GOAL_TRANSITIONS: Final[dict[str, set[str]]] = {
    "pending": {"active"},
    "active": {"blocked", "completed"},
    "blocked": {"active"},
    "completed": {"reopened"},
    "reopened": {"active", "blocked", "completed"},
}

_EVIDENCE_TYPES = {
    "test_run", "workflow_run", "pr_head_sha", "merge_commit", "artifact_sha256",
    "runtime_canary", "deployment_revision", "database_evidence", "review_approval",
}

_CONTENT_METRICS = {
    "global_rank", "visits_total", "unique_visitors", "bounce_rate", "pages_per_visit",
    "visit_duration", "traffic_sources_desktop", "traffic_sources_mobile", "traffic_by_country",
}


@dataclass(frozen=True)
class BundleFile:
    path: str
    size: int
    sha256: str
    mode: int
    is_symlink: bool
    read_text: Callable[[], str | None]


def _repo(workspace_id: str) -> Path:
    if _RUNTIME is None:
        raise RuntimeError("Skill supply-chain tools are not registered")
    return _RUNTIME._repo(workspace_id)


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_relative(value: str, *, field: str = "path") -> str:
    normalized = str(value or "").strip().replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    pure = PurePosixPath(normalized)
    if not normalized or pure.is_absolute() or ".." in pure.parts or any(part in {".git", "node_modules", ".env"} for part in pure.parts):
        raise ValueError(f"{field} is unsafe")
    return pure.as_posix()


def _bundle(repo: Path, bundle_path: str) -> tuple[dict[str, Any], list[BundleFile]]:
    selected = safe_repo_path(repo, bundle_path)
    if not selected.exists():
        raise FileNotFoundError(bundle_path)
    if selected.is_dir():
        files: list[BundleFile] = []
        total = 0
        for path in sorted(item for item in selected.rglob("*") if item.is_file()):
            relative = path.relative_to(selected).as_posix()
            if len(files) >= _MAX_MEMBERS:
                raise ValueError("skill directory exceeds the bounded member limit")
            size = path.stat().st_size
            if size > _MAX_MEMBER_BYTES:
                raise ValueError(f"member exceeds bounded size: {relative}")
            total += size
            if total > _MAX_UNCOMPRESSED_BYTES:
                raise ValueError("skill directory exceeds the bounded total size")
            payload = path.read_bytes()
            files.append(BundleFile(
                path=relative,
                size=size,
                sha256=hashlib.sha256(payload).hexdigest(),
                mode=path.stat().st_mode,
                is_symlink=path.is_symlink(),
                read_text=lambda p=path, s=size: p.read_text("utf-8") if s <= _MAX_TEXT_BYTES and p.suffix.casefold() in _TEXT_SUFFIXES else None,
            ))
        return {"kind":"directory","path":bundle_path,"bytes":total,"sha256":_canonical_hash([{"path":x.path,"sha256":x.sha256} for x in files]),"memberCount":len(files)}, files
    if selected.suffix.casefold() not in {".zip", ".skill"}:
        raise ValueError("bundle_path must be a directory, .zip or .skill archive")
    if selected.stat().st_size > _MAX_ARCHIVE_BYTES:
        raise ValueError("archive exceeds compressed size limit")
    archive_sha=hashlib.sha256(selected.read_bytes()).hexdigest()
    files=[]
    with zipfile.ZipFile(selected) as archive:
        infos=archive.infolist()
        if len(infos)>_MAX_MEMBERS or sum(i.file_size for i in infos)>_MAX_UNCOMPRESSED_BYTES:
            raise ValueError("archive exceeds bounded limits")
        for info in infos:
            if info.is_dir(): continue
            pure=PurePosixPath(info.filename)
            if pure.is_absolute() or ".." in pure.parts or info.flag_bits & 1 or info.file_size>_MAX_MEMBER_BYTES:
                raise ValueError(f"unsafe archive member: {info.filename}")
            payload=archive.read(info); suffix=pure.suffix.casefold(); mode=(info.external_attr>>16)&0o177777
            def reader(data=payload, ok=suffix in _TEXT_SUFFIXES and len(payload)<=_MAX_TEXT_BYTES):
                if not ok: return None
                try: return data.decode("utf-8")
                except UnicodeDecodeError: return None
            files.append(BundleFile(pure.as_posix(),len(payload),hashlib.sha256(payload).hexdigest(),mode,(mode&0o170000)==0o120000,reader))
    return {"kind":"archive","path":bundle_path,"bytes":selected.stat().st_size,"sha256":archive_sha,"memberCount":len(files)}, files


def _skill(files):
    items=[x for x in files if PurePosixPath(x.path).name.casefold()=="skill.md"]
    return sorted(items,key=lambda x:(len(PurePosixPath(x.path).parts),x.path))[0] if items else None


def _frontmatter(text):
    if not text.startswith("---\n") or "\n---" not in text[4:]: return {},["invalid frontmatter"]
    end=text.find("\n---",4); out={}; errors=[]; current=""
    for line in text[4:end].splitlines():
        if not line.strip(): continue
        if line[:1].isspace() and current: out[current]=(out[current]+" "+line.strip()).strip(); continue
        if ":" not in line: errors.append(f"invalid line: {line[:120]}"); continue
        current,value=line.split(":",1); current=current.strip(); out[current]=value.strip().strip('"').strip("'")
    return out,errors


def _scan(files):
    findings=[]; urls=set(); suffixes=Counter(); scripts=0; binaries=0
    for item in files:
        suffix=PurePosixPath(item.path).suffix.casefold(); suffixes[suffix or "<none>"]+=1
        scripts+=suffix in _SCRIPT_SUFFIXES; binaries+=suffix in _BINARY_SUFFIXES
        if item.is_symlink: findings.append({"severity":"P0","family":"SYMLINK_MEMBER","path":item.path})
        if suffix in _BINARY_SUFFIXES: findings.append({"severity":"P1","family":"BINARY_MEMBER","path":item.path})
        text=item.read_text()
        if text is None: continue
        for family,severity,pattern in (("SECRET_LIKE_MARKER","P0",_SECRET_MARKER),("GENERIC_SHELL_EXECUTION","P0",_SHELL_CODE),("PACKAGE_INSTALLATION","P1",_INSTALL_CODE),("NETWORK_ACCESS","P1",_NETWORK_CODE),("ENVIRONMENT_SECRET_ACCESS","P1",_ENV_ACCESS),("FREE_FILE_MUTATION","P1",_FILE_WRITE),("ABSOLUTE_HOST_PATH","P1",_ABSOLUTE_PATH)):
            m=pattern.search(text)
            if m and len(findings)<_MAX_FINDINGS: findings.append({"severity":severity,"family":family,"path":item.path,"line":text.count("\n",0,m.start())+1,"matchedValueReturned":False})
        for m in _URL.finditer(text):
            u=m.group(0).rstrip(".,;:"); urls.add("<redacted-url>" if _SECRET_MARKER.search(u) else u.split("?",1)[0]+("?<redacted>" if "?" in u else ""))
    findings.sort(key=lambda x:({"P0":0,"P1":1,"P2":2}.get(x["severity"],9),x["family"],x["path"]))
    return {"scripts":scripts,"binaries":binaries,"suffixCounts":dict(sorted(suffixes.items())),"externalUrls":sorted(urls)[:100],"findings":findings[:_MAX_FINDINGS],"codeExecuted":False,"secretValuesReturned":False}


def _source_name(files):
    item=_skill(files)
    if not item: return ""
    fm,_=_frontmatter(item.read_text() or ""); return str(fm.get("name") or "").casefold().strip()


def skill_supply_chain_inventory():
    """List archive-derived preview tools and enforced truth boundaries."""
    tools=[{"name":name,"sourceSkill":source,"kind":profile["kind"],"priority":profile["priority"],"mutates":False} for source,profile in SOURCE_PROFILES.items() for name in profile["tools"]]
    return {"ok":True,"status":"SKILL_SUPPLY_CHAIN_READY","sourceSkills":SOURCE_PROFILES,"toolCount":len(tools),"tools":tools,"truthBoundary":{"originalScriptsExecuted":False,"genericShellAvailable":False,"networkDiscoveryPerformed":False,"foreignPackagesInstalled":False,"databaseMutated":False}}


def skill_archive_inspect(workspace_id,bundle_path):
    """Inspect one repository-scoped skill archive without executing code."""
    meta,files=_bundle(_repo(workspace_id),bundle_path); item=_skill(files)
    return {"ok":True,"status":"SKILL_ARCHIVE_INSPECTION_READY","bundle":meta,"skillMd":{"present":bool(item),"path":item.path if item else None,"sha256":item.sha256 if item else None},"members":[{"path":x.path,"bytes":x.size,"sha256":x.sha256,"isSymlink":x.is_symlink,"executableBit":bool(x.mode&0o111)} for x in files[:500]],"risk":_scan(files),"mutationPerformed":False}


def skill_validate(workspace_id,bundle_path):
    """Validate metadata, structure and execution risks without activation."""
    meta,files=_bundle(_repo(workspace_id),bundle_path); scan=_scan(files); item=_skill(files); errors=[]; warnings=[]; fm={}
    if not item: errors.append({"family":"SKILL_MD_MISSING"})
    else:
        fm,front_errors=_frontmatter(item.read_text() or ""); errors += [{"family":"FRONTMATTER_INVALID","message":x} for x in front_errors]
        name=str(fm.get("name") or ""); desc=str(fm.get("description") or "")
        if not name or not _SAFE_ID.fullmatch(name): errors.append({"family":"SKILL_NAME_INVALID"})
        if not desc: errors.append({"family":"SKILL_DESCRIPTION_MISSING"})
    for f in scan["findings"]: (errors if f["severity"]=="P0" else warnings).append(f)
    source=str(fm.get("name") or _source_name(files)).casefold()
    return {"ok":not errors,"status":"SKILL_VALID" if not errors else "SKILL_VALIDATION_BLOCKED","bundleSha256":meta["sha256"],"frontmatter":{k:v for k,v in fm.items() if k in {"name","description","license"}},"sourceProfile":SOURCE_PROFILES.get(source),"errors":errors[:_MAX_FINDINGS],"warnings":warnings[:_MAX_FINDINGS],"activationAllowed":False,"codeExecuted":False}


def skill_capability_extract(workspace_id,bundle_path):
    """Extract static capability candidates from one skill bundle."""
    meta,files=_bundle(_repo(workspace_id),bundle_path); source=_source_name(files); text="\n".join(filter(None,(x.read_text() for x in files)))[:2_000_000]
    scripts=[x.path for x in files if PurePosixPath(x.path).suffix.casefold() in _SCRIPT_SUFFIXES]
    verbs=sorted(set(re.findall(r"\b(?:create|generate|inspect|validate|search|list|save|update|analy[sz]e|render|verify|compile|install|write|read|fetch|audit|plan|compare|track)\b",text,re.I)))[:80]
    payload={"source":source,"verbs":[x.casefold() for x in verbs],"scripts":scripts,"placeholders":sorted(set(_PLACEHOLDER.findall(text)))[:100]}
    return {"ok":True,"status":"SKILL_CAPABILITY_MODEL_READY","bundleSha256":meta["sha256"],"sourceSkill":source or None,"knownProfile":SOURCE_PROFILES.get(source),**payload,"requiresNetworkCandidate":bool(_NETWORK_CODE.search(text)),"requiresSecretsCandidate":bool(_ENV_ACCESS.search(text)),"mutatesFilesCandidate":bool(_FILE_WRITE.search(text)),"installsDependenciesCandidate":bool(_INSTALL_CODE.search(text)),"genericShellCandidate":bool(_SHELL_CODE.search(text)),"capabilityHash":_canonical_hash(payload),"truthNotice":"Static candidates only; no original code executed."}


def skill_tool_contract_preview(workspace_id,bundle_path):
    """Build non-active Sovereign tool contracts from one validated skill."""
    validation=skill_validate(workspace_id,bundle_path); capability=skill_capability_extract(workspace_id,bundle_path); source=str(capability.get("sourceSkill") or "unknown-skill"); profile=SOURCE_PROFILES.get(source)
    tools=[{"name":name,"annotations":{"readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False},"ownerScopeRequired":True,"evidenceRequiredForSuccess":True,"active":False} for name in (profile or {}).get("tools",[])]
    return {"ok":bool(validation["ok"] and tools),"status":"TOOL_CONTRACT_PREVIEW_READY" if validation["ok"] and tools else "TOOL_CONTRACT_PREVIEW_BLOCKED","sourceSkill":source,"bundleSha256":validation["bundleSha256"],"proposedTools":tools,"validationErrors":validation["errors"],"capabilityHash":capability["capabilityHash"],"activationPath":["inspection","contract","isolated_patch","tests","draft_pr","exact_head_ci","immutable_image","live_canary"],"mutationPerformed":False}


def skill_catalog_search(workspace_id,cache_path,query,limit=20):
    """Search a versioned local JSON skill cache without network access."""
    path=safe_repo_path(_repo(workspace_id),cache_path,must_exist=True)
    if path.suffix.casefold() != ".json" or path.stat().st_size>2_000_000: raise ValueError("invalid cache_path")
    payload=json.loads(path.read_text("utf-8")); flat=[]
    def walk(v):
        if len(flat)>=_MAX_CATALOG_ITEMS:return
        if isinstance(v,list):
            for x in v: walk(x)
        elif isinstance(v,dict):
            if set(map(str.casefold,map(str,v))) & {"name","skill","skill_name","description","repo","repository"}: flat.append(v)
            else:
                for x in v.values(): walk(x)
    walk(payload); tokens=re.findall(r"[a-z0-9][a-z0-9_-]+",str(query).casefold()); matches=[]
    for x in flat:
        safe={"name":str(x.get("name") or x.get("skill") or x.get("skill_name") or "")[:160],"description":str(x.get("description") or x.get("summary") or "")[:500],"repository":str(x.get("repository") or x.get("repo") or x.get("source") or "")[:240],"revision":str(x.get("revision") or x.get("sha") or x.get("commit") or "")[:80]}
        hay=" ".join(safe.values()).casefold(); score=sum(3 if t in safe["name"].casefold() else 1 for t in tokens if t in hay)
        if score: matches.append({**safe,"score":score,"importAllowed":False})
    matches.sort(key=lambda x:(-x["score"],x["name"])); return {"ok":True,"status":"LOCAL_SKILL_CATALOG_RESULTS","cacheSha256":hashlib.sha256(path.read_bytes()).hexdigest(),"matches":matches[:max(1,min(int(limit),50))],"networkAccessed":False,"skillsInstalled":False}


def skill_candidate_compare(candidate,existing_tools):
    """Compare candidate terms against existing tool names and descriptions."""
    tokens=set(re.findall(r"[a-z0-9][a-z0-9_-]+",f"{candidate.get('name','')} {candidate.get('description','')}".casefold())); overlaps=[]
    for tool in existing_tools[:500]:
        shared=sorted(tokens & set(re.findall(r"[a-z0-9][a-z0-9_-]+",f"{tool.get('name','')} {tool.get('description',tool.get('sourceSkill',''))}".casefold())))
        if shared: overlaps.append({"tool":str(tool.get("name") or "")[:160],"sharedTerms":shared[:20],"overlapScore":len(shared)})
    overlaps.sort(key=lambda x:(-x["overlapScore"],x["tool"])); top=overlaps[0]["overlapScore"] if overlaps else 0
    return {"ok":True,"status":"SKILL_CANDIDATE_COMPARISON_READY","classification":"already_covered" if top>=4 else "partially_covered" if top>=2 else "new_capability_candidate","overlaps":overlaps[:20],"installationAllowed":False}


def goal_runtime_schema_plan():
    """Return evidence-bound PostgreSQL goal schema plan."""
    tables={"sovereign_goals":["goal_id","owner_id","repository","title","goal_type","status","initial_hash","created_by_run_id"],"sovereign_goal_edges":["parent_goal_id","child_goal_id","edge_type"],"sovereign_goal_events":["event_id","goal_id","from_status","to_status","causal_run_id","event_hash"],"sovereign_goal_evidence":["evidence_id","goal_id","evidence_type","external_identity","sha256"],"sovereign_goal_blockers":["blocker_id","goal_id","family","active"]}
    return {"ok":True,"status":"GOAL_RUNTIME_SCHEMA_PLAN_READY","tables":tables,"progressScale":_PROGRESS_SCALE,"freeProgressInputAllowed":False,"transitionTable":{k:sorted(v) for k,v in _ALLOWED_GOAL_TRANSITIONS.items()},"databaseMutated":False,"planSha256":_canonical_hash(tables)}


def goal_progress_projection(children,required_evidence,evidence):
    """Calculate progress from completed required children and verified evidence."""
    required_children=[x for x in children[:500] if bool(x.get("required",True))]; total=sum(max(1,min(int(x.get("weight",1)),100)) for x in required_children); done=sum(max(1,min(int(x.get("weight",1)),100)) for x in required_children if str(x.get("status") or "").casefold()=="completed")
    required=sorted({str(x).strip() for x in required_evidence if str(x).strip()}); verified={str(x.get("type") or "").strip() for x in evidence[:500] if bool(x.get("verified"))}; invalid=sorted((set(required)|verified)-_EVIDENCE_TYPES); denom=total+len(required); numer=done+len(set(required)&verified)
    return {"ok":not invalid,"status":"GOAL_PROGRESS_PROJECTED" if not invalid else "GOAL_PROGRESS_BLOCKED","progressPermille":_PROGRESS_SCALE if denom==0 else numer*_PROGRESS_SCALE//denom,"missingEvidence":sorted(set(required)-verified),"invalidEvidenceTypes":invalid,"freeProgressInputUsed":False}


def goal_transition_preview(current_status,target_status,goal_type,children,required_evidence,evidence,active_blockers):
    """Validate a goal transition without mutation."""
    current=str(current_status).casefold(); target=str(target_status).casefold(); reasons=[]; allowed=target in _ALLOWED_GOAL_TRANSITIONS.get(current,set()); projection=goal_progress_projection(children,required_evidence,evidence); blockers=[x for x in active_blockers[:200] if bool(x.get("active",True))]
    if not allowed: reasons.append("transition_not_allowed")
    if target=="completed":
        if blockers: reasons.append("active_blockers_present")
        if projection["missingEvidence"]: reasons.append("required_evidence_missing")
        if any(bool(x.get("required",True)) and str(x.get("status") or "").casefold()!="completed" for x in children[:500]): reasons.append("required_children_incomplete")
    return {"ok":allowed and not reasons and projection["ok"],"status":"GOAL_TRANSITION_ALLOWED" if allowed and not reasons and projection["ok"] else "GOAL_TRANSITION_BLOCKED","goalType":str(goal_type)[:80],"from":current,"to":target,"reasons":reasons,"progress":projection,"mutationPerformed":False}


def goal_reconcile_runtime_plan(goal,runtime_evidence):
    """Propose reopen/block actions from supplied verified runtime identities."""
    status=str(goal.get("status") or "").casefold(); required=set(map(str,goal.get("requiredEvidence",[]))); valid=[x for x in runtime_evidence[:300] if bool(x.get("verified"))]; missing=sorted(required-{str(x.get("type") or "") for x in valid}); failed=[x for x in runtime_evidence[:300] if str(x.get("conclusion") or "").casefold() in {"failure","cancelled","timed_out","rolled_back"}]; actions=[]
    if status=="completed" and (missing or failed): actions.append("reopen_goal")
    if failed: actions.append("attach_active_blocker")
    return {"ok":not actions,"status":"GOAL_RUNTIME_CONSISTENT" if not actions else "GOAL_RUNTIME_RECONCILIATION_REQUIRED","missingEvidence":missing,"failedOrRolledBackEvidence":[{"type":x.get("type"),"identity":str(x.get("identity") or "")[:200],"conclusion":x.get("conclusion")} for x in failed],"proposedActions":sorted(set(actions)),"mutationPerformed":False}


def document_plan(workspace_id,source_path,document_type,title,author="",requested_renderer="auto",theme="sovereign-default"):
    """Build deterministic document artifact plan without compilation."""
    path=safe_repo_path(_repo(workspace_id),source_path,must_exist=True); payload=path.read_bytes()
    renderer=requested_renderer if requested_renderer in {"typst","gotenberg"} else "typst" if str(document_type).casefold() in {"report","audit","architecture","academic","kdp"} else "gotenberg"
    core={"source":{"path":source_path,"bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest()},"documentType":str(document_type),"title":str(title)[:240],"author":str(author)[:160],"renderer":renderer,"theme":str(theme)[:80],"limits":{"maxPdfBytes":_MAX_PDF_BYTES,"networkAccess":False}}
    return {"ok":bool(core["title"]),"status":"DOCUMENT_PLAN_READY" if core["title"] else "DOCUMENT_PLAN_BLOCKED",**core,"expectedArtifacts":["document.pdf","artifact-manifest.json","verification-report.json"],"planSha256":_canonical_hash(core),"mutationPerformed":False}


def typst_document_prepare_plan(workspace_id,source_path,title,author="",document_type="report"):
    """Plan package-free isolated Typst workspace files."""
    base=document_plan(workspace_id,source_path,document_type,title,author,"typst"); files=["main.typ","source.md","document-manifest.json","theme.typ"]
    return {**base,"status":"TYPST_PREPARE_PLAN_READY" if base["ok"] else "TYPST_PREPARE_PLAN_BLOCKED","workspaceFiles":files,"typstUniversePackagesAllowed":False,"compileExecution":"dedicated_document_worker_only","filesWritten":False}


def pdf_artifact_verify(workspace_id,pdf_path):
    """Verify PDF signature, size, hash and bounded pdfinfo metadata."""
    path=safe_repo_path(_repo(workspace_id),pdf_path,must_exist=True); data=path.read_bytes()
    if path.suffix.casefold()!=".pdf" or len(data)>_MAX_PDF_BYTES: raise ValueError("invalid PDF path or size")
    signature=data.startswith(b"%PDF-"); eof=b"%%EOF" in data[-4096:]; info={"available":False}; binary=shutil.which("pdfinfo")
    if binary:
        result=subprocess.run([binary,str(path)],capture_output=True,text=True,timeout=20,check=False); info={"available":True,"exitCode":result.returncode}
    ok=signature and eof and len(data)>=20 and (not info["available"] or info["exitCode"]==0)
    return {"ok":ok,"status":"PDF_ARTIFACT_VERIFIED" if ok else "PDF_ARTIFACT_INVALID","bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"pdfSignature":signature,"eofMarker":eof,"pdfinfo":info,"documentContentReturned":False,"mutationPerformed":False}


def template_catalog_list(category=""):
    """List curated template contracts; raw archive templates remain inactive."""
    selected=str(category).casefold(); items=[{"id":k,**v} for k,v in sorted(CURATED_TEMPLATES.items()) if not selected or v["category"]==selected]
    return {"ok":True,"status":"CURATED_TEMPLATE_CATALOG_READY","templates":items,"rawArchiveTemplatesActive":False,"genericOutputPathAllowed":False,"catalogSha256":_canonical_hash(CURATED_TEMPLATES)}


def template_contract_audit(template):
    """Audit proposed template contract for unsafe paths, secrets and shell behavior."""
    errors=[]; warnings=[]; template_id=str(template.get("id") or template.get("name") or "").casefold().replace("_","-")
    if not _SAFE_ID.fullmatch(template_id): errors.append("invalid_template_id")
    files=[]
    for item in template.get("files",[])[:100]:
        try: files.append(_safe_relative(str(item),field="template file"))
        except ValueError: errors.append("unsafe_template_file_path")
    rendered=json.dumps(template,ensure_ascii=False,sort_keys=True)
    if _SECRET_MARKER.search(rendered): errors.append("secret_like_marker")
    if _SHELL_CODE.search(rendered): errors.append("generic_shell_contract")
    if _INSTALL_CODE.search(rendered): warnings.append("dependency_installation_candidate")
    if _ABSOLUTE_PATH.search(rendered): errors.append("absolute_host_path")
    return {"ok":not errors,"status":"TEMPLATE_CONTRACT_VALID" if not errors else "TEMPLATE_CONTRACT_BLOCKED","templateId":template_id,"safeFiles":sorted(set(files)),"errors":sorted(set(errors)),"warnings":sorted(set(warnings)),"activationAllowed":False,"mutationPerformed":False}


def template_generation_plan(template_id,parameters,output_root=".sovereign-generated"):
    """Render deterministic file hashes/content from a curated template without writing."""
    selected=str(template_id).casefold(); contract=CURATED_TEMPLATES.get(selected); errors=[]; root=_safe_relative(output_root,field="output_root")
    if not contract: errors.append("unknown_template_id"); merged={}
    else:
        merged=dict(contract["optional"]); allowed=set(contract["required"])|set(contract["optional"])
        for key in contract["required"]:
            if not parameters.get(key): errors.append(f"missing_required_parameter:{key}")
        for key,value in parameters.items():
            if key in contract["forbidden"]: errors.append(f"forbidden_parameter:{key}")
            elif key not in allowed: errors.append(f"unknown_parameter:{key}")
            else: merged[key]=value
    files=[]
    if contract and not errors:
        for relative in contract["files"]:
            content=(json.dumps({"templateId":selected,"parameters":merged},ensure_ascii=False,sort_keys=True,indent=2)+"\n") if relative.endswith(".json") else f"# {merged.get('project_name') or merged.get('surface_name') or merged.get('topic') or selected}\n\nCurated Sovereign template preview; not runtime success.\n"
            files.append({"path":f"{root}/{selected}/{relative}","bytes":len(content.encode()),"sha256":hashlib.sha256(content.encode()).hexdigest(),"content":content})
    return {"ok":bool(files) and not errors,"status":"TEMPLATE_GENERATION_PLAN_READY" if files and not errors else "TEMPLATE_GENERATION_PLAN_BLOCKED","templateId":selected,"parameters":merged,"errors":errors,"files":files,"filesWritten":False,"dependenciesInstalled":False,"planSha256":_canonical_hash([{k:x[k] for k in ("path","sha256")} for x in files])}


def template_candidate_save_preview(name,category,description,features,technologies,schema):
    """Normalize a new template candidate without saving it."""
    proposal={"id":str(name).casefold().replace("_","-").replace(" ","-"),"category":str(category)[:80],"description":" ".join(str(description).split())[:800],"features":sorted(set(map(str,features[:100]))),"technologies":sorted(set(map(str,technologies[:100]))),"schema":schema,"files":["README.md","project.manifest.json"]}; audit=template_contract_audit(proposal); markdown=f"# {name}\n\n{proposal['description']}\n\n```json\n{json.dumps(schema,ensure_ascii=False,sort_keys=True,indent=2)}\n```\n"
    return {"ok":audit["ok"],"status":"TEMPLATE_SAVE_PREVIEW_READY" if audit["ok"] else "TEMPLATE_SAVE_PREVIEW_BLOCKED","proposal":proposal,"audit":audit,"canonicalMarkdown":markdown if audit["ok"] else "","templateSaved":False}


def template_project_structure_analyze(workspace_id,project_path,max_files=500):
    """Analyze bounded repository subdirectory for template integration surfaces."""
    repo=_repo(workspace_id); root=safe_repo_path(repo,project_path); limit=max(1,min(int(max_files),1000)); files=[]; risks=[]
    if not root.is_dir(): raise ValueError("project_path must be a directory")
    for path in sorted(x for x in root.rglob("*") if x.is_file())[:limit]:
        rel=path.relative_to(root).as_posix(); data=path.read_bytes(); files.append({"path":rel,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
        if path.suffix.casefold() in _TEXT_SUFFIXES and len(data)<=_MAX_TEXT_BYTES:
            text=data.decode("utf-8",errors="replace")
            for family,pattern in (("absolute_path",_ABSOLUTE_PATH),("package_install",_INSTALL_CODE),("shell",_SHELL_CODE),("secret_marker",_SECRET_MARKER)):
                if pattern.search(text): risks.append({"family":family,"path":rel,"matchedValueReturned":False})
    return {"ok":True,"status":"PROJECT_STRUCTURE_ANALYSIS_READY","files":files,"fileCount":len(files),"riskCandidates":risks[:_MAX_FINDINGS],"secretValuesReturned":False,"mutationPerformed":False}


def github_solution_evaluate(capability,candidates):
    """Evaluate supplied GitHub metadata without network, install or execution."""
    out=[]
    for x in candidates[:30]:
        score=min(max(int(x.get("stars") or 0)//100,0),25)+(20 if x.get("licenseApproved") else 0)+(15 if int(x.get("daysSinceRelease") or 9999)<=180 else 5 if int(x.get("daysSinceRelease") or 9999)<=730 else 0)+(15 if x.get("reproducibleInstall") else 0)+(10 if x.get("maintainerActive") else 0)-min(int(x.get("openSecurityAdvisories") or 0)*15,45)-(10 if x.get("binaryDownloads") else 0)
        out.append({"repository":str(x.get("repository") or "")[:240],"revision":str(x.get("revision") or "")[:80],"score":max(0,min(score,100)),"eligibleForIntegrationPlan":score>=60 and bool(x.get("licenseApproved")) and int(x.get("openSecurityAdvisories") or 0)==0})
    out.sort(key=lambda x:(-x["score"],x["repository"])); return {"ok":bool(out),"status":"GITHUB_SOLUTION_EVALUATION_READY" if out else "GITHUB_SOLUTION_EVALUATION_BLOCKED","capability":str(capability)[:240],"candidates":out,"packagesInstalled":False,"candidateCodeExecuted":False,"networkAccessed":False}


def github_solution_integration_plan(capability,candidate,integration_surface):
    """Build pinned integration/rollback plan for one supplied candidate."""
    evaluation=github_solution_evaluate(capability,[candidate]); item=evaluation["candidates"][0] if evaluation["candidates"] else {}; revision=str(candidate.get("revision") or ""); blockers=[]
    if not re.fullmatch(r"[0-9a-f]{40}",revision): blockers.append("full_commit_sha_required")
    if not item.get("eligibleForIntegrationPlan"): blockers.append("quality_or_security_gate_failed")
    return {"ok":not blockers,"status":"GITHUB_SOLUTION_INTEGRATION_PLAN_READY" if not blockers else "GITHUB_SOLUTION_INTEGRATION_PLAN_BLOCKED","evaluation":item,"plan":{"dependencyPin":revision or None,"integrationSurface":str(integration_surface)[:240],"sandbox":"github_actions_only","requiredTests":["license","dependency_audit","integration","rollback"]},"blockers":blockers,"mutationPerformed":False}


def android_ui_contract_audit(workspace_id,path="src",max_findings=160):
    """Audit TSX/CSS for Android touch, overflow and accessibility candidates."""
    repo=_repo(workspace_id); root=safe_repo_path(repo,path); findings=[]; patterns=(("TOUCH_TARGET_BELOW_44PX","P1",re.compile(r"(?:height|min-height|width|min-width)\s*:\s*(?:[1-3]?\d|4[0-3])px",re.I)),("FONT_BELOW_14PX","P2",re.compile(r"font-size\s*:\s*(?:[1-9]|1[0-3])px",re.I)),("DESKTOP_HOVER_WITHOUT_FOCUS","P1",re.compile(r":hover",re.I)),("CLICKABLE_DIV_CANDIDATE","P1",re.compile(r"<div[^>]+onClick=",re.I)),("IMAGE_WITHOUT_ALT_CANDIDATE","P1",re.compile(r"<img(?![^>]+\balt=)[^>]*>",re.I)))
    if not root.is_dir(): raise ValueError("path must be a directory")
    for file in sorted(x for x in root.rglob("*") if x.is_file() and x.suffix.casefold() in {".tsx",".ts",".jsx",".js",".css",".scss"}):
        text=file.read_text("utf-8",errors="replace")
        for family,severity,pattern in patterns:
            for m in pattern.finditer(text): findings.append({"severity":severity,"family":family,"path":file.relative_to(repo).as_posix(),"line":text.count("\n",0,m.start())+1,"status":"STATIC_CANDIDATE"})
            if len(findings)>=max(1,min(int(max_findings),_MAX_FINDINGS)): break
        if len(findings)>=max(1,min(int(max_findings),_MAX_FINDINGS)): break
    return {"ok":True,"status":"ANDROID_UI_CONTRACT_AUDIT_READY","findings":findings,"mutationPerformed":False,"truthNotice":"Static candidates require device evidence."}


def android_ui_surface_map(workspace_id,path="src"):
    """Map bounded Android-facing views, routes, stores and API calls."""
    repo=_repo(workspace_id); root=safe_repo_path(repo,path); views=[]; routes=[]; stores=[]; calls=[]
    if not root.is_dir(): raise ValueError("path must be a directory")
    for file in sorted(x for x in root.rglob("*") if x.is_file() and x.suffix.casefold() in {".tsx",".ts",".jsx",".js"}):
        text=file.read_text("utf-8",errors="replace"); rel=file.relative_to(repo).as_posix()
        views += [{"name":n,"path":rel} for n in re.findall(r"(?:function|const|class)\s+([A-Z][A-Za-z0-9_]*)",text)[:30]]
        if re.search(r"(?:createSlice|zustand|useStore|configureStore)",text,re.I): stores.append({"path":rel})
        routes += [{"route":m.group(1)[:200],"path":rel} for m in re.finditer(r"(?:path\s*=\s*|navigate\(|to=)[\s{]*['\"]([^'\"]+)['\"]",text)]
        calls += [{"endpoint":m.group(1).split("?",1)[0][:240],"path":rel} for m in re.finditer(r"(?:fetch\(|axios\.(?:get|post)|api\.(?:get|post))\s*['\"`]([^'\"`]+)",text,re.I)]
    return {"ok":True,"status":"ANDROID_UI_SURFACE_MAP_READY","views":views[:_MAX_FINDINGS],"routes":routes[:_MAX_FINDINGS],"stores":stores[:_MAX_FINDINGS],"apiCalls":calls[:_MAX_FINDINGS],"runtimeConnectivityProven":False,"mutationPerformed":False}


def domain_analytics_capability_status():
    """Report provider configuration metadata without a provider request."""
    provider=os.getenv("SOVEREIGN_DOMAIN_ANALYTICS_PROVIDER","").casefold().strip(); configured=provider in {"similarweb","dataforseo","custom"}
    return {"ok":configured,"status":"DOMAIN_ANALYTICS_PROVIDER_CONFIGURED" if configured else "DOMAIN_ANALYTICS_PROVIDER_NOT_CONFIGURED","provider":provider or None,"protectedCredentialConfigured":bool(os.getenv("SOVEREIGN_DOMAIN_ANALYTICS_CREDENTIAL_FILE","")),"providerRequestPerformed":False,"secretValuesReturned":False}


def domain_analytics_query_plan(domain,start_month,end_month,metrics,countries=None,granularity="monthly"):
    """Normalize provider-neutral analytics query without consuming credits."""
    d=str(domain).casefold().strip().removeprefix("https://").removeprefix("http://").split("/",1)[0]; errors=[]; selected=sorted(set(map(str,metrics)))
    if not _SAFE_DOMAIN.fullmatch(d): errors.append("invalid_domain")
    if not _MONTH.fullmatch(str(start_month)) or not _MONTH.fullmatch(str(end_month)) or start_month>end_month: errors.append("invalid_month_range")
    unknown=sorted(set(selected)-_CONTENT_METRICS)
    if unknown: errors.append("unsupported_metrics")
    payload={"domain":d,"startMonth":start_month,"endMonth":end_month,"metrics":selected,"countries":sorted(set(map(str,countries or []))),"granularity":granularity}
    return {"ok":not errors,"status":"DOMAIN_ANALYTICS_QUERY_PLAN_READY" if not errors else "DOMAIN_ANALYTICS_QUERY_PLAN_BLOCKED","query":payload,"errors":errors,"unknownMetrics":unknown,"creditsConsumed":False,"querySha256":_canonical_hash(payload)}


def content_research_plan(topic,target_keyword,audience,comparison_objects,claims_to_verify,price_date="",require_homepage_captures=False):
    """Build separated research, evidence, writing and audit plan."""
    errors=[]
    if not str(topic).strip(): errors.append("topic_required")
    if not str(audience).strip(): errors.append("audience_required")
    if price_date:
        try: date.fromisoformat(price_date)
        except ValueError: errors.append("price_date_must_be_iso_date")
    plan={"topic":str(topic)[:300],"targetKeyword":str(target_keyword)[:160],"audience":str(audience)[:240],"comparisonObjects":sorted(set(map(str,comparison_objects[:50]))),"claimsToVerify":sorted(set(map(str,claims_to_verify[:100]))),"priceDate":price_date or None,"captureTargets":sorted(set(map(str,comparison_objects[:50]))) if require_homepage_captures else [],"roles":["research","evidence","writer","claim_auditor","artifact_verifier"]}
    return {"ok":not errors,"status":"CONTENT_RESEARCH_PLAN_READY" if not errors else "CONTENT_RESEARCH_PLAN_BLOCKED","plan":plan,"errors":errors,"writingStarted":False,"planSha256":_canonical_hash(plan)}


def content_source_ledger_audit(entries):
    """Validate source identity, dates and claim binding."""
    errors=[]; normalized=[]; seen=set()
    for i,x in enumerate(entries[:500],1):
        source=str(x.get("sourceId") or ""); url=str(x.get("url") or ""); retrieved=str(x.get("retrievedAt") or ""); claims=x.get("claimIds") if isinstance(x.get("claimIds"),list) else []
        if not source or source in seen: errors.append({"entry":i,"family":"source_id_missing_or_duplicate"})
        seen.add(source)
        if not url.startswith("https://"): errors.append({"entry":i,"family":"https_url_required"})
        try: date.fromisoformat(retrieved[:10])
        except ValueError: errors.append({"entry":i,"family":"retrieval_date_invalid"})
        if not claims: errors.append({"entry":i,"family":"claim_binding_required"})
        normalized.append({"sourceId":source[:120],"url":url.split("?",1)[0]+("?<redacted>" if "?" in url else ""),"retrievedAt":retrieved[:40],"claimIds":list(map(str,claims[:100])),"sourceClass":str(x.get("sourceClass") or "unknown")[:80]})
    return {"ok":not errors,"status":"CONTENT_SOURCE_LEDGER_VALID" if not errors else "CONTENT_SOURCE_LEDGER_BLOCKED","entries":normalized,"errors":errors[:_MAX_FINDINGS],"ledgerSha256":_canonical_hash(normalized),"claimsWritten":False}


def content_claim_audit(claims,ledger_entries):
    """Audit claims for source binding, dated prices and fabricated review risk."""
    ledger={str(x.get("sourceId") or ""):x for x in ledger_entries[:500]}; findings=[]
    for i,x in enumerate(claims[:500],1):
        cid=str(x.get("claimId") or f"claim-{i}"); text=str(x.get("text") or ""); sources=list(map(str,x.get("sourceIds",[]))) if isinstance(x.get("sourceIds"),list) else []
        if not sources: findings.append({"severity":"P0","family":"UNSOURCED_CLAIM","claimId":cid})
        if any(s not in ledger for s in sources): findings.append({"severity":"P0","family":"UNKNOWN_SOURCE_BINDING","claimId":cid})
        if re.search(r"\b(?:best|leading|#1|cheapest|fastest|beste|führend)\b",text,re.I): findings.append({"severity":"P1","family":"SUPERLATIVE_REQUIRES_EVIDENCE","claimId":cid})
        if re.search(r"(?:[$€£]\s?\d|\d[,.]\d{2}\s?(?:USD|EUR|GBP))",text,re.I) and not x.get("priceDate"): findings.append({"severity":"P1","family":"PRICE_DATE_MISSING","claimId":cid})
        if x.get("reviewClaim") and not x.get("firstPartyTest") and not x.get("thirdPartyExperienceSource"): findings.append({"severity":"P0","family":"FABRICATED_REVIEW_RISK","claimId":cid})
    return {"ok":not any(x["severity"]=="P0" for x in findings),"status":"CONTENT_CLAIMS_AUDITED" if not any(x["severity"]=="P0" for x in findings) else "CONTENT_CLAIMS_BLOCKED","findings":findings[:_MAX_FINDINGS],"contentPublished":False}


def register(mcp,runtime):
    global _RUNTIME,_REGISTERED
    _RUNTIME=runtime
    if _REGISTERED:return
    for tool in (skill_supply_chain_inventory,skill_archive_inspect,skill_validate,skill_capability_extract,skill_tool_contract_preview,skill_catalog_search,skill_candidate_compare,goal_runtime_schema_plan,goal_progress_projection,goal_transition_preview,goal_reconcile_runtime_plan,document_plan,typst_document_prepare_plan,pdf_artifact_verify,template_catalog_list,template_contract_audit,template_generation_plan,template_candidate_save_preview,template_project_structure_analyze,github_solution_evaluate,github_solution_integration_plan,android_ui_contract_audit,android_ui_surface_map,domain_analytics_capability_status,domain_analytics_query_plan,content_research_plan,content_source_ledger_audit,content_claim_audit):
        mcp.tool(annotations=READ_ONLY)(tool)
    _REGISTERED=True
