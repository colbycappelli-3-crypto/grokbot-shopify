"""Offline runtimes for registered logical agents."""
from .compliance import ComplianceScreeningAgent
from .dossier_agent import OpportunityDossierAgent
from .economics import UnitEconomicsAgent
from .market import MarketResearchAgent
from .supplier import SupplierResearchAgent
from .trend import TrendDiscoveryAgent
from .validation import ProductValidationAgent

__all__ = [
    "ComplianceScreeningAgent",
    "MarketResearchAgent",
    "OpportunityDossierAgent",
    "ProductValidationAgent",
    "SupplierResearchAgent",
    "TrendDiscoveryAgent",
    "UnitEconomicsAgent",
    "default_runtimes",
]


def default_runtimes() -> dict:
    agents = [
        TrendDiscoveryAgent(),
        MarketResearchAgent(),
        ProductValidationAgent(),
        UnitEconomicsAgent(),
        ComplianceScreeningAgent(),
        SupplierResearchAgent(),
        OpportunityDossierAgent(),
    ]
    return {agent.agent_id: agent for agent in agents}
