import logging
from typing import List, Dict, Set, Optional

logger = logging.getLogger(__name__)

class ResearchNetworkGraph:
    """
    Provenance-required researcher/collaboration graph (Section 7.8).
    An edge between two researchers can ONLY be added where a documented basis 
    exists in the underlying corpus (e.g., co-authorship, citation), preventing 
    speculative or hallucinated connections.
    """
    def __init__(self):
        self.researchers: Set[str] = set()
        self.edges: List[Dict[str, str]] = []

    def add_provenance_edge(self, researcher_a: str, researcher_b: str, basis_document_id: str, basis_type: str = "co_authorship") -> bool:
        """
        Adds a connection only if a valid document basis is provided.
        basis_type: 'co_authorship', 'citation', 'shared_supervisor', etc.
        """
        if not basis_document_id:
            logger.error(f"Rejected edge {researcher_a} <-> {researcher_b}: No provenance basis document ID provided.")
            return False
            
        # Prevent duplicate edges
        for edge in self.edges:
            if (edge["source"] == researcher_a and edge["target"] == researcher_b and edge["basis"] == basis_document_id):
                logger.info(f"Edge {researcher_a} <-> {researcher_b} already exists with this basis.")
                return True

        self.researchers.add(researcher_a)
        self.researchers.add(researcher_b)
        
        new_edge = {
            "source": researcher_a,
            "target": researcher_b,
            "basis": basis_document_id,
            "basis_type": basis_type
        }
        self.edges.append(new_edge)
        logger.info(f"Added provenance edge: {researcher_a} <-> {researcher_b} (Basis: {basis_type} in doc {basis_document_id})")
        return True

    def get_collaborators(self, researcher_id: str) -> List[Dict[str, str]]:
        """Returns all researchers connected to the given researcher, with the provenance basis."""
        collaborators = []
        for edge in self.edges:
            if edge["source"] == researcher_id:
                collaborators.append({"researcher": edge["target"], "basis": edge["basis"], "type": edge["basis_type"]})
            elif edge["target"] == researcher_id:
                collaborators.append({"researcher": edge["source"], "basis": edge["basis"], "type": edge["basis_type"]})
        return collaborators

    def get_graph_stats(self) -> Dict[str, int]:
        return {
            "total_researchers": len(self.researchers),
            "total_provenance_edges": len(self.edges)
        }