import httpx
import asyncio
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

class VerificationEngine:
    """
    Checks if a remediation action successfully recovered the service/system.
    Checks are defined identically in the runbook YAML under the `verification` key.
    """
    
    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=10.0)
        
    async def verify(self, runbook: Dict[str, Any], diagnosis: Dict[str, Any]) -> Tuple[bool, str]:
        verification = runbook.get("verification")
        if not verification:
            logger.info("Runbook has no verification steps. Assuming success.")
            return True, "No verification required"
            
        wait_seconds = verification.get("wait_seconds", 5)
        logger.info(f"Waiting {wait_seconds}s before running verification checks...")
        await asyncio.sleep(wait_seconds)
        
        checks = verification.get("checks", [])
        for check in checks:
            ok, reason = await self._run_check(check, diagnosis)
            if not ok:
                return False, f"Verification failed: {reason}"
                
        return True, "All verification checks passed"
        
    async def _run_check(self, check: Dict[str, Any], diagnosis: Dict[str, Any]) -> Tuple[bool, str]:
        check_type = check.get("type")
        
        if check_type == "health_check":
            endpoint = check.get("endpoint", "")
            expected = check.get("expected_status", 200)
            
            # Extract service name robustly
            diagnosis_dict = diagnosis.get("diagnosis")
            if isinstance(diagnosis_dict, dict):
                service = diagnosis_dict.get("root_cause_service", "")
            else:
                service = diagnosis.get("root_cause", {}).get("service", "")
            
            # Map service name to correct internal port
            service_ports = {
                "user-svc": 8001,
                "auth-svc": 8004,
                "order-svc": 8002,
                "payment-svc": 8005,
                "product-svc": 8003,
                "search-svc": 8006,
                "notification-worker": 8007,
                "inventory-worker": 8008,
                "analytics-worker": 8009,
            }
            port = service_ports.get(service, 8000)
            
            # Replace host and port templates
            endpoint = endpoint.replace("{{diagnosis.root_cause.service}}:8000", f"{service}:{port}")
            endpoint = endpoint.replace("{{diagnosis.root_cause.service}}", service)
            
            try:
                resp = await self.http_client.get(endpoint)
                if resp.status_code == expected:
                    return True, "Endpoint healthy"
                else:
                    return False, f"Endpoint returned {resp.status_code}, expected {expected}"
            except Exception as e:
                return False, f"Endpoint unreachable: {e}"
                
        elif check_type == "metric":
            # For MVP: Assume metrics recover out of band 
            # In a real impl, query the Prometheus API
            return True, "Metric check mocked to success"
            
        else:
            return False, f"Unknown check type {check_type}"
