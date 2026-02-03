"""
Football Transfer Network Dashboard

Interactive Streamlit dashboard for exploring football transfer relationships.
"""

import streamlit as st
import networkx as nx
import plotly.graph_objects as go
import pandas as pd
from typing import Dict, List, Tuple
from graph_builder.ingest import get_data_source
from graph_builder.graph import TransferGraph


# Page config
st.set_page_config(
    page_title="Football Transfer Network",
    page_icon="⚽",
    layout="wide"
)


@st.cache_resource
def load_graph():
    """Load and build transfer graph (cached)."""
    with st.spinner("Loading transfer data..."):
        data_source = get_data_source("jsonl", data_dir="data/extracted")
        graph_builder = TransferGraph(data_source)
        graph = graph_builder.build()
    return graph_builder, graph


def build_network_visualization(
    graph: nx.Graph,
    layout: str = "spring",
    highlight_nodes: List[str] = None
) -> go.Figure:
    """
    Build interactive network visualization with Plotly.
    
    Args:
        graph: NetworkX graph to visualize
        layout: Layout algorithm ("spring", "circular", "kamada_kawai")
        highlight_nodes: List of node IDs to highlight
    """
    # Get layout positions
    if layout == "spring":
        pos = nx.spring_layout(graph, k=0.5, iterations=50, seed=42)
    elif layout == "circular":
        pos = nx.circular_layout(graph)
    elif layout == "kamada_kawai":
        pos = nx.kamada_kawai_layout(graph)
    else:
        pos = nx.spring_layout(graph, seed=42)
    
    # Create edge traces
    edge_traces = []
    
    for edge in graph.edges(data=True):
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        
        edge_data = edge[2]
        fee = edge_data.get('fee_amount', 0) or 0
        
        # Edge width based on fee
        width = 0.5 + min(fee / 10, 5)  # Scale fee to reasonable width
        
        edge_trace = go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode='lines',
            line=dict(
                width=width,
                color='rgba(125, 125, 125, 0.3)'
            ),
            hoverinfo='text',
            text=f"{edge_data.get('player_name', 'Unknown')}<br>"
                 f"Fee: €{fee}M<br>"
                 f"Season: {edge_data.get('season', 'N/A')}",
            showlegend=False
        )
        edge_traces.append(edge_trace)
    
    # Create node traces (separate for players and clubs)
    player_nodes = [n for n in graph.nodes() if n.startswith("player:")]
    club_nodes = [n for n in graph.nodes() if n.startswith("club:")]
    
    # Player nodes
    player_x = [pos[node][0] for node in player_nodes]
    player_y = [pos[node][1] for node in player_nodes]
    player_text = [graph.nodes[node].get('name', node) for node in player_nodes]
    
    player_trace = go.Scatter(
        x=player_x,
        y=player_y,
        mode='markers',
        marker=dict(
            size=8,
            color='lightblue',
            line=dict(width=1, color='white')
        ),
        text=player_text,
        hoverinfo='text',
        name='Players',
        showlegend=True
    )
    
    # Club nodes
    club_x = [pos[node][0] for node in club_nodes]
    club_y = [pos[node][1] for node in club_nodes]
    club_text = [graph.nodes[node].get('name', node) for node in club_nodes]
    club_sizes = [10 + graph.degree(node) * 2 for node in club_nodes]  # Size by connections
    
    club_trace = go.Scatter(
        x=club_x,
        y=club_y,
        mode='markers+text',
        marker=dict(
            size=club_sizes,
            color='coral',
            line=dict(width=2, color='white')
        ),
        text=club_text,
        textposition="top center",
        textfont=dict(size=10),
        hoverinfo='text',
        name='Clubs',
        showlegend=True
    )
    
    # Combine traces
    fig = go.Figure(data=edge_traces + [player_trace, club_trace])
    
    fig.update_layout(
        title="Football Transfer Network",
        showlegend=True,
        hovermode='closest',
        margin=dict(b=0, l=0, r=0, t=40),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor='white',
        height=700
    )
    
    return fig


def build_club_network_visualization(club_graph: nx.DiGraph) -> go.Figure:
    """Build simplified club-to-club network."""
    # Use better spacing for readability
    pos = nx.spring_layout(club_graph, k=2.0, iterations=100, seed=42)
    
    # Create edges with curved arrows
    edge_traces = []
    
    for edge in club_graph.edges(data=True):
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        
        edge_data = edge[2]
        num_transfers = edge_data.get('num_transfers', 0)
        total_fees = edge_data.get('total_fees', 0)
        
        edge_trace = go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode='lines',
            line=dict(
                width=0.5 + min(num_transfers * 0.5, 3),  # Thinner edges
                color='rgba(150, 150, 150, 0.3)'
            ),
            hoverinfo='text',
            text=f"<b>{edge_data.get('from_club_name')} → {edge_data.get('to_club_name')}</b><br>"
                 f"Transfers: {num_transfers}<br>"
                 f"Total Fees: €{total_fees:.1f}M",
            showlegend=False
        )
        edge_traces.append(edge_trace)
    
    # Create club nodes - only show text on hover to reduce clutter
    node_x = [pos[node][0] for node in club_graph.nodes()]
    node_y = [pos[node][1] for node in club_graph.nodes()]
    node_names = [club_graph.nodes[node].get('name', node) for node in club_graph.nodes()]
    node_degrees = [club_graph.degree(node) for node in club_graph.nodes()]
    node_sizes = [10 + degree * 3 for degree in node_degrees]
    
    # Color by activity level
    max_degree = max(node_degrees) if node_degrees else 1
    node_colors = [f'rgba(255, {int(140 - (degree/max_degree)*100)}, {int(100 - (degree/max_degree)*50)}, 0.8)' 
                   for degree in node_degrees]
    
    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode='markers',  # Remove text overlay
        marker=dict(
            size=node_sizes,
            color=node_colors,
            line=dict(width=1.5, color='white'),
            symbol='circle'
        ),
        text=node_names,
        customdata=node_degrees,
        hovertemplate='<b>%{text}</b><br>Connections: %{customdata}<extra></extra>',
        showlegend=False
    )
    
    fig = go.Figure(data=edge_traces + [node_trace])
    
    fig.update_layout(
        title="Club-to-Club Transfer Network<br><sub>Hover over nodes to see club names | Larger nodes = more transfer activity</sub>",
        showlegend=False,
        hovermode='closest',
        margin=dict(b=20, l=20, r=20, t=60),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        plot_bgcolor='#f8f9fa',
        height=800,
        # Enable zoom and pan
        dragmode='pan'
    )
    
    return fig


def main():
    """Main dashboard application."""
    st.title("⚽ Football Transfer Network Explorer")
    st.markdown("Explore transfer relationships between clubs and players")
    
    # Load data
    graph_builder, graph = load_graph()
    
    # Sidebar controls
    st.sidebar.header("Controls")
    
    view_mode = st.sidebar.radio(
        "View Mode",
        ["Club Network", "Full Network", "Player Search"],
        help="Choose what to visualize"
    )
    
    # Display stats
    stats = graph_builder.get_graph_stats()
    st.sidebar.markdown("### Dataset Stats")
    st.sidebar.metric("Players", stats['num_players'])
    st.sidebar.metric("Clubs", stats['num_clubs'])
    st.sidebar.metric("Transfers", stats['num_transfers'])
    
    # Main content based on view mode
    if view_mode == "Club Network":
        st.header("Club-to-Club Transfer Network")
        st.markdown("Visualizing aggregated transfers between clubs. **Hover over nodes** to see club names.")
        
        club_graph = graph_builder.get_club_transfer_network()
        
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            min_transfers = st.slider(
                "Minimum transfers between clubs",
                min_value=1,
                max_value=10,
                value=2,  # Default to 2 for cleaner graph
                help="Filter out clubs with fewer transfer relationships"
            )
        with col2:
            max_clubs = st.slider(
                "Maximum clubs to show",
                min_value=10,
                max_value=200,
                value=50,
                help="Limit number of clubs for better performance"
            )
        
        # Filter graph
        filtered_club_graph = club_graph.copy()
        edges_to_remove = [
            (u, v) for u, v, d in filtered_club_graph.edges(data=True)
            if d.get('num_transfers', 0) < min_transfers
        ]
        filtered_club_graph.remove_edges_from(edges_to_remove)
        
        # Remove isolated nodes
        isolated = list(nx.isolates(filtered_club_graph))
        filtered_club_graph.remove_nodes_from(isolated)
        
        # Limit to top N most connected clubs
        if filtered_club_graph.number_of_nodes() > max_clubs:
            # Sort clubs by degree (number of connections)
            club_degrees = dict(filtered_club_graph.degree())
            top_clubs = sorted(club_degrees.items(), key=lambda x: x[1], reverse=True)[:max_clubs]
            top_club_ids = [club[0] for club in top_clubs]
            filtered_club_graph = filtered_club_graph.subgraph(top_club_ids).copy()
        
        if filtered_club_graph.number_of_nodes() > 0:
            fig = build_club_network_visualization(filtered_club_graph)
            st.plotly_chart(fig, use_container_width=True)
            
            # Top transfers table
            st.subheader("Top Transfer Routes")
            transfer_data = []
            for u, v, d in filtered_club_graph.edges(data=True):
                transfer_data.append({
                    'From': d.get('from_club_name'),
                    'To': d.get('to_club_name'),
                    'Transfers': d.get('num_transfers'),
                    'Total Fees (€M)': f"{d.get('total_fees', 0):.1f}"
                })
            
            df = pd.DataFrame(transfer_data)
            df = df.sort_values('Transfers', ascending=False).head(20)
            st.dataframe(df, use_container_width=True)
        else:
            st.warning("No transfers meet the filter criteria")
    
    elif view_mode == "Full Network":
        st.header("Complete Transfer Network")
        st.markdown("Players and clubs connected by transfers")
        
        # Layout selection
        layout = st.selectbox(
            "Layout Algorithm",
            ["spring", "circular", "kamada_kawai"],
            index=0
        )
        
        # Sample for performance if graph is too large
        if graph.number_of_nodes() > 500:
            st.warning(f"Large graph ({graph.number_of_nodes()} nodes). Showing sample...")
            # Sample nodes
            sampled_nodes = list(graph.nodes())[:500]
            subgraph = graph.subgraph(sampled_nodes)
        else:
            subgraph = graph
        
        fig = build_network_visualization(subgraph, layout=layout)
        st.plotly_chart(fig, use_container_width=True)
    
    elif view_mode == "Player Search":
        st.header("Player Transfer History")
        
        # Get all players
        player_nodes = [n for n in graph.nodes() if n.startswith("player:")]
        player_names = {
            graph.nodes[n].get('name', n): n.replace("player:", "")
            for n in player_nodes
        }
        
        selected_player_name = st.selectbox(
            "Select a player",
            options=sorted(player_names.keys())
        )
        
        if selected_player_name:
            player_tm_id = player_names[selected_player_name]
            player_node = f"player:{player_tm_id}"
            
            # Player info
            player_data = graph.nodes[player_node]
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Name", player_data.get('name', 'N/A'))
            with col2:
                st.metric("Position", player_data.get('position', 'N/A'))
            with col3:
                st.metric("Current Club", player_data.get('current_club', 'N/A'))
            
            # Transfer history
            st.subheader("Transfer History")
            transfers = graph_builder.get_player_transfer_history(player_tm_id)
            
            if transfers:
                transfer_df = pd.DataFrame(transfers)
                st.dataframe(transfer_df, use_container_width=True)
                
                # Visualize player's network
                st.subheader("Player's Transfer Network")
                
                # Get ego network (player + connected clubs)
                ego_graph = nx.ego_graph(graph, player_node, radius=1)
                fig = build_network_visualization(ego_graph, layout="circular")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No transfer history available for this player")


if __name__ == "__main__":
    main()
