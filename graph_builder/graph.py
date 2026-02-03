"""
Graph construction layer for transfer network.

Builds NetworkX graph from ingested data with proper separation of concerns.
"""

import networkx as nx
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict
from .ingest import Player, Transfer, DataSource


class TransferGraph:
    """
    Transfer network graph builder.
    
    Nodes: Players, Clubs
    Edges: Transfers (player -> club relationships with temporal + financial attributes)
    """
    
    def __init__(self, data_source: DataSource):
        """
        Initialize graph builder.
        
        Args:
            data_source: Data source to load players and transfers from
        """
        self.data_source = data_source
        self.graph = nx.MultiDiGraph()  # MultiDiGraph allows multiple edges between same nodes
        self._players: Dict[str, Player] = {}
        self._clubs: Set[str] = set()
        self._club_lookup: Dict[str, str] = {}
    
    def build(self) -> nx.MultiDiGraph:
        """
        Build the complete transfer network graph.
        
        Returns:
            NetworkX MultiDiGraph with players, clubs, and transfers
        """
        # Load data
        players = self.data_source.load_players()
        transfers = self.data_source.load_transfers()
        self._club_lookup = self.data_source.get_club_lookup()
        
        # Build player index
        for player in players:
            self._players[player.tm_id] = player
        
        # Add nodes
        self._add_player_nodes(players)
        self._add_club_nodes(transfers)
        
        # Add edges
        self._add_transfer_edges(transfers)
        
        return self.graph
    
    def _normalize_club_name(self, club_name: Optional[str]) -> Optional[str]:
        """Normalize club name using lookup table."""
        if not club_name:
            return None
        return self._club_lookup.get(club_name, club_name)
    
    def _add_player_nodes(self, players: List[Player]):
        """Add player nodes to graph."""
        for player in players:
            self.graph.add_node(
                f"player:{player.tm_id}",
                node_type="player",
                tm_id=player.tm_id,
                name=player.name,
                date_of_birth=player.date_of_birth,
                nationality=player.nationality,
                position=player.position,
                current_club=player.current_club,
                scraped_at=player.scraped_at
            )
    
    def _add_club_nodes(self, transfers: List[Transfer]):
        """Add club nodes to graph (extracted from transfers)."""
        clubs = set()
        
        for transfer in transfers:
            if transfer.from_club:
                clubs.add(self._normalize_club_name(transfer.from_club))
            if transfer.to_club:
                clubs.add(self._normalize_club_name(transfer.to_club))
        
        self._clubs = clubs
        
        for club in clubs:
            if club:  # Skip None values
                self.graph.add_node(
                    f"club:{club}",
                    node_type="club",
                    name=club
                )
    
    def _add_transfer_edges(self, transfers: List[Transfer]):
        """
        Add transfer edges to graph.
        
        Creates edges: club -> player -> club (transfer flow)
        """
        for transfer in transfers:
            player_node = f"player:{transfer.player_tm_id}"
            from_club = self._normalize_club_name(transfer.from_club)
            to_club = self._normalize_club_name(transfer.to_club)
            
            # Skip if player node doesn't exist
            if player_node not in self.graph:
                # Create minimal player node from transfer data
                self.graph.add_node(
                    player_node,
                    node_type="player",
                    tm_id=transfer.player_tm_id,
                    name=transfer.player_name,
                    scraped_at=transfer.scraped_at
                )
            
            # Add edge: from_club -> player (if from_club exists)
            if from_club:
                from_club_node = f"club:{from_club}"
                if from_club_node not in self.graph:
                    self.graph.add_node(from_club_node, node_type="club", name=from_club)
                
                self.graph.add_edge(
                    from_club_node,
                    player_node,
                    edge_type="departure",
                    player_name=transfer.player_name,
                    transfer_date=transfer.transfer_date,
                    season=transfer.season,
                    transfer_type=transfer.transfer_type,
                    fee_amount=transfer.fee_amount,
                    fee_currency=transfer.fee_currency,
                    is_disclosed=transfer.is_disclosed,
                    has_addons=transfer.has_addons,
                    is_loan_fee=transfer.is_loan_fee,
                    notes=transfer.notes,
                    source_url=transfer.source_url,
                    scraped_at=transfer.scraped_at
                )
            
            # Add edge: player -> to_club (if to_club exists)
            if to_club:
                to_club_node = f"club:{to_club}"
                if to_club_node not in self.graph:
                    self.graph.add_node(to_club_node, node_type="club", name=to_club)
                
                self.graph.add_edge(
                    player_node,
                    to_club_node,
                    edge_type="arrival",
                    player_name=transfer.player_name,
                    transfer_date=transfer.transfer_date,
                    season=transfer.season,
                    transfer_type=transfer.transfer_type,
                    fee_amount=transfer.fee_amount,
                    fee_currency=transfer.fee_currency,
                    is_disclosed=transfer.is_disclosed,
                    has_addons=transfer.has_addons,
                    is_loan_fee=transfer.is_loan_fee,
                    notes=transfer.notes,
                    source_url=transfer.source_url,
                    scraped_at=transfer.scraped_at
                )
    
    def get_club_transfer_network(self) -> nx.DiGraph:
        """
        Get club-to-club transfer network (simplified view).
        
        Returns directed graph where:
        - Nodes are clubs
        - Edges are aggregated transfers between clubs
        """
        club_graph = nx.DiGraph()
        
        # Track transfers between clubs
        club_transfers = defaultdict(lambda: defaultdict(list))
        
        # Iterate through original graph to find club->player->club paths
        for player_node in self.graph.nodes():
            if not player_node.startswith("player:"):
                continue
            
            # Get clubs this player came from and went to
            from_clubs = [
                edge[0] for edge in self.graph.in_edges(player_node)
                if edge[0].startswith("club:")
            ]
            to_clubs = [
                edge[1] for edge in self.graph.out_edges(player_node)
                if edge[1].startswith("club:")
            ]
            
            # Create club-to-club edges for each transfer
            for from_club in from_clubs:
                for to_club in to_clubs:
                    # Get transfer details
                    edge_data = self.graph.get_edge_data(player_node, to_club)
                    if edge_data:
                        # MultiDiGraph returns dict of edges, get first one
                        transfer_data = list(edge_data.values())[0]
                        club_transfers[from_club][to_club].append({
                            'player': self.graph.nodes[player_node].get('name'),
                            'player_tm_id': self.graph.nodes[player_node].get('tm_id'),
                            'fee_amount': transfer_data.get('fee_amount'),
                            'fee_currency': transfer_data.get('fee_currency'),
                            'season': transfer_data.get('season'),
                            'transfer_date': transfer_data.get('transfer_date'),
                        })
        
        # Build simplified club network
        for from_club, destinations in club_transfers.items():
            from_club_name = self.graph.nodes[from_club]['name']
            club_graph.add_node(from_club, name=from_club_name)
            
            for to_club, transfers in destinations.items():
                to_club_name = self.graph.nodes[to_club]['name']
                club_graph.add_node(to_club, name=to_club_name)
                
                # Aggregate metrics
                total_fees = sum(
                    t['fee_amount'] for t in transfers
                    if t['fee_amount'] is not None
                )
                num_transfers = len(transfers)
                
                club_graph.add_edge(
                    from_club,
                    to_club,
                    num_transfers=num_transfers,
                    total_fees=total_fees,
                    transfers=transfers,
                    from_club_name=from_club_name,
                    to_club_name=to_club_name
                )
        
        return club_graph
    
    def get_player_transfer_history(self, player_tm_id: str) -> List[Dict]:
        """
        Get chronological transfer history for a player.
        
        Args:
            player_tm_id: Transfermarkt player ID
        
        Returns:
            List of transfer dicts sorted by date
        """
        player_node = f"player:{player_tm_id}"
        if player_node not in self.graph:
            return []
        
        transfers = []
        
        # Get arrivals (player -> club)
        for _, to_club, edge_data in self.graph.out_edges(player_node, data=True):
            if to_club.startswith("club:"):
                transfers.append({
                    'type': 'arrival',
                    'club': self.graph.nodes[to_club]['name'],
                    'date': edge_data.get('transfer_date'),
                    'season': edge_data.get('season'),
                    'fee_amount': edge_data.get('fee_amount'),
                    'fee_currency': edge_data.get('fee_currency'),
                    'transfer_type': edge_data.get('transfer_type'),
                })
        
        # Sort by date (handle None values)
        transfers.sort(
            key=lambda x: x.get('date') or x.get('season') or '',
            reverse=True
        )
        
        return transfers
    
    def get_graph_stats(self) -> Dict:
        """Get summary statistics about the graph."""
        player_nodes = [n for n in self.graph.nodes() if n.startswith("player:")]
        club_nodes = [n for n in self.graph.nodes() if n.startswith("club:")]
        
        return {
            'num_players': len(player_nodes),
            'num_clubs': len(club_nodes),
            'num_transfers': self.graph.number_of_edges(),
            'total_nodes': self.graph.number_of_nodes(),
        }
