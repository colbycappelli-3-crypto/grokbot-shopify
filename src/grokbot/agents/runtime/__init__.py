"""Offline runtimes for registered logical agents."""
from .compliance import ComplianceScreeningAgent
from .dossier_agent import OpportunityDossierAgent
from .drafts import ListingDraftAgent, PodProductDraftAgent
from .economics import UnitEconomicsAgent
from .market import MarketResearchAgent
from .research import ResearchConnectorAgent
from .services import ServiceCommunicationDraftAgent, ServiceResearchAgent, ServiceWorkflowAgent
from .supplier import SupplierResearchAgent
from .trend import TrendDiscoveryAgent
from .validation import ProductValidationAgent

__all__ = [
    "ComplianceScreeningAgent",
    "ListingDraftAgent",
    "MarketResearchAgent",
    "OpportunityDossierAgent",
    "PodProductDraftAgent",
    "ProductValidationAgent",
    "ResearchConnectorAgent",
    "ServiceCommunicationDraftAgent",
    "ServiceResearchAgent",
    "ServiceWorkflowAgent",
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
        ResearchConnectorAgent(),
        PodProductDraftAgent(),
        ListingDraftAgent(),
        ServiceResearchAgent(),
        ServiceWorkflowAgent(),
        ServiceCommunicationDraftAgent(),
    ]
    return {agent.agent_id: agent for agent in agents}
