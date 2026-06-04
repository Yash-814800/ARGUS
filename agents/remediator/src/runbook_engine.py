import os
import yaml
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class RunbookEngine:
    """
    Loads YAML runbooks from disk and matches incoming Root Cause 
    Analyses (RCAs) to specific executable action plans.
    """
    
    def __init__(self, runbook_dir: str = None):
        if runbook_dir is None:
            # Default to the 'runbooks' folder natively beside 'src'
            runbook_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runbooks"))
        self.runbook_dir = runbook_dir
        self.runbooks = self._load_runbooks()
        
    def _load_runbooks(self) -> dict:
        loaded = {}
        if not os.path.exists(self.runbook_dir):
            logger.warning(f"Runbook directory {self.runbook_dir} does not exist.")
            return loaded
            
        for filename in os.listdir(self.runbook_dir):
            if filename.endswith((".yml", ".yaml")):
                path = os.path.join(self.runbook_dir, filename)
                try:
                    with open(path, "r") as f:
                        rb = yaml.safe_load(f)
                        if rb and "id" in rb:
                            loaded[rb["id"]] = rb
                            logger.info(f"Loaded runbook: {rb['id']}")
                except Exception as e:
                    logger.error(f"Failed to load runbook {path}: {e}")
        return loaded
        
    def find_match(self, diagnosis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Matches a diagnosis (e.g. category='memory_leak') to the first applicable runbook.
        """
        diagnosis_dict = diagnosis.get("diagnosis")
        if isinstance(diagnosis_dict, dict):
            category = diagnosis_dict.get("root_cause_category")
            service = diagnosis_dict.get("root_cause_service")
            recommended_runbook = diagnosis_dict.get("recommended_runbook")
            confidence = diagnosis.get("confidence", 0)
        else:
            rc = diagnosis.get("root_cause", {})
            category = rc.get("category") or diagnosis.get("root_cause_category")
            service = rc.get("service") or diagnosis.get("root_cause_service")
            recommended_runbook = diagnosis.get("recommended_runbook")
            confidence = rc.get("confidence") or diagnosis.get("confidence", 0)
        
        if not category:
            logger.warning("Diagnosis missing root_cause category")
            return None

        # Normalized mapping for categories
        mapped_category = category
        if category == "resource_exhaustion":
            mapped_category = "memory_leak"
        elif category == "database":
            mapped_category = "database_overload"
        elif category == "network":
            mapped_category = "network_partition"
        elif category == "application_error":
            mapped_category = "memory_leak"

        # Also support mapping via recommended_runbook if category doesn't match directly
        if recommended_runbook == "restart_service" and mapped_category not in ["memory_leak", "database_overload"]:
            mapped_category = "memory_leak"
        elif recommended_runbook == "circuit_break" and mapped_category != "network_partition":
            mapped_category = "network_partition"

        logger.info(f"Finding runbook for service={service}, category={category} (mapped to {mapped_category}), recommended_runbook={recommended_runbook}")
            
        for rb_id, rb in self.runbooks.items():
            matches = rb.get("matches", {})
            
            # Category match
            if matches.get("root_cause_category") == mapped_category:
                # Confidence match
                min_conf = matches.get("confidence_minimum", 0)
                if confidence >= min_conf:
                    logger.info(f"Matched diagnosis to runbook: {rb_id}")
                    return rb
                    
        logger.info(f"No matching runbook found for category='{category}' (mapped to '{mapped_category}')")
        return None
        
    def render_action(self, action: Dict[str, Any], diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interpolates template variables like `{{diagnosis.root_cause.service}}` in the action params.
        """
        import copy
        
        rendered = copy.deepcopy(action)
        params = rendered.get("params", {})
        
        # Extract service name robustly
        diagnosis_dict = diagnosis.get("diagnosis")
        if isinstance(diagnosis_dict, dict):
            service = diagnosis_dict.get("root_cause_service", "unknown")
        else:
            rc = diagnosis.get("root_cause", {})
            service = rc.get("service") or diagnosis.get("root_cause_service", "unknown")

        # Super simple {{key}} interpolator for MVP
        for k, v in params.items():
            if isinstance(v, str) and "{{" in v:
                if "{{diagnosis.root_cause.service}}" in v:
                    params[k] = v.replace("{{diagnosis.root_cause.service}}", service)
                    
        rendered["params"] = params
        return rendered
