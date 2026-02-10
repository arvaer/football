"""
Football Transfer Network Dashboard

Interactive Streamlit dashboard for exploring football transfer relationships.
"""

import streamlit as st
import networkx as nx
import plotly.graph_objects as go
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from graph_builder.ingest import get_data_source
from graph_builder.graph import TransferGraph
from graph_builder.transition_stats_loader import get_transition_stats_loader
from player_valuations.valuation_pathways.model import RegimeSwitchingLogModel
from player_valuations.valuation_pathways.model.regimes import RegimeParameters
from player_valuations.valuation_pathways.engine.simulator import run_simulation


# Page config
st.set_page_config(
    page_title="Football Transfer Network",
    page_icon="⚽",
    layout="wide"
)


# ============================================================================
# Helper Functions
# ============================================================================

def get_player_age(date_of_birth: str) -> Optional[float]:
    """Calculate player age from date of birth."""
    if not date_of_birth:
        return None
    try:
        dob = datetime.fromisoformat(date_of_birth)
        today = datetime.now()
        return (today - dob).days / 365.25
    except (ValueError, TypeError):
        return None


def get_position_group(position: str) -> str:
    """Map position to group (GK, DEF, MID, FWD)."""
    if not position:
        return 'UNK'
    pos = position.upper()
    if pos == 'GK': 
        return 'GK'
    elif pos in ['CB', 'LB', 'RB', 'LWB', 'RWB']:
        return 'DEF'
    elif pos in ['DM', 'CM', 'AM', 'LM', 'RM']:
        return 'MID'
    elif pos in ['LW', 'RW', 'CF', 'ST']:
        return 'FWD'
    return 'UNK'


def get_age_band(age: float) -> str:
    """Convert age to band."""
    if age < 21: 
        return 'U21'
    elif age < 25: 
        return '21-24'
    elif age < 29: 
        return '25-28'
    else: 
        return '29+'


def get_player_market_value(
    player_node: str,
    graph: nx.Graph,
    use_enriched: bool = False
) -> Optional[float]:
    """Get current market value for a player.
    
    Args:
        player_node: Player node ID
        graph: NetworkX graph
        use_enriched: If True, try enriched profiles (not yet implemented)
    
    Returns:
        Market value in millions, or None if not available
    """
    # For now, get from latest transfer edge
    edges = list(graph.edges(player_node, data=True))
    
    if not edges:
        return None
    
    # Find most recent transfer with market value
    transfers_with_mv = [
        e[2] for e in edges 
        if e[2].get('market_value_at_transfer') is not None
    ]
    
    if not transfers_with_mv:
        return None
    
    # Sort by transfer date (most recent first)
    transfers_with_mv.sort(
        key=lambda x: x.get('transfer_date', ''),
        reverse=True
    )
    
    return transfers_with_mv[0].get('market_value_at_transfer')


def get_latest_batch_results() -> Optional[Path]:
    """Get the most recent batch valuation results directory."""
    summary_dir = Path("data/summary")
    
    if not summary_dir.exists():
        return None
    
    batch_dirs = list(summary_dir.glob("batch_valuations_*"))
    
    if not batch_dirs:
        return None
    
    # Sort by modification time (most recent first)
    latest_dir = max(batch_dirs, key=lambda p: p.stat().st_mtime)
    
    return latest_dir


@st.cache_data
def simulate_player_valuation(
    current_value: float,
    age: float,
    position: str,
    months: int = 6,
    n_paths: int = 1000,
    seed: int = 42
):
    """Run valuation simulation for a player.
    
    Args:
        current_value: Current market value in millions
        age: Player age
        position: Player position
        months: Simulation horizon
        n_paths: Number of Monte Carlo paths
        seed: Random seed
    
    Returns:
        SimulationResult or None if stratum data not available
    """
    loader = get_transition_stats_loader()
    
    # Get player stratum
    age_band = get_age_band(age)
    pos_group = get_position_group(position)
    
    # Get stats for stay and move scenarios
    stats_stay = loader.get_stratum_stats(age, pos_group, "stay")
    stats_move = loader.get_stratum_stats(age, pos_group, "moved")
    
    if not stats_stay or not stats_move:
        return None
    
    # Create regime parameters (using 30-day rates)
    regime_params = {
        "stay": RegimeParameters(
            mu=stats_stay.mu_rate_per_30day,
            sigma=stats_stay.sigma_rate_per_30day
        ),
        "moved": RegimeParameters(
            mu=stats_move.mu_rate_per_30day,
            sigma=stats_move.sigma_rate_per_30day
        )
    }
    
    model = RegimeSwitchingLogModel(regime_params)
    
    # Define scenarios
    half_months = months // 2
    scenario_paths = {
        f"Stay {months}m": ["stay"] * months,
        f"Move immediately": ["moved"] * months,
        f"Move after {half_months}m": ["stay"] * half_months + ["moved"] * (months - half_months)
    }
    
    # Run simulation
    result = run_simulation(
        V0=current_value,
        scenario_paths=scenario_paths,
        model=model,
        months=months,
        n_paths=n_paths,
        seed=seed
    )
    
    # Add stratum metadata to result
    result.stratum_info = {
        "age_band": age_band,
        "position": pos_group,
        "stats_stay": stats_stay,
        "stats_move": stats_move,
    }
    
    return result


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
        ["Club Network", "Full Network", "Player Search", "Batch Valuation EDA"],
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
                
                # ============================================================
                # Valuation Projection Section
                # ============================================================
                st.markdown("---")
                st.subheader("📈 Valuation Projection")
                
                # Get player attributes
                player_age = get_player_age(player_data.get('date_of_birth'))
                player_position = player_data.get('position')
                current_mv = get_player_market_value(player_node, graph)
                
                if player_age and player_position:
                    age_band = get_age_band(player_age)
                    pos_group = get_position_group(player_position)
                    
                    # Show player classification
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Age", f"{player_age:.1f} ({age_band})")
                    with col2:
                        st.metric("Position Group", pos_group)
                    with col3:
                        if current_mv:
                            st.metric("Current Value", f"€{current_mv:.2f}M")
                        else:
                            st.metric("Current Value", "N/A")
                    
                    # Manual override for market value
                    use_manual_mv = st.checkbox("Override market value", value=not bool(current_mv))
                    
                    if use_manual_mv or not current_mv:
                        initial_value = st.number_input(
                            "Initial valuation (€M)",
                            min_value=0.1,
                            max_value=200.0,
                            value=current_mv if current_mv else 2.0,
                            step=0.5
                        )
                    else:
                        initial_value = current_mv
                    
                    # Simulation controls
                    st.markdown("#### Simulation Parameters")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        sim_months = st.slider(
                            "Time horizon (months)",
                            min_value=3,
                            max_value=12,
                            value=6,
                            step=1
                        )
                    
                    with col2:
                        sim_paths = st.select_slider(
                            "Number of simulations",
                            options=[100, 500, 1000, 2000, 5000],
                            value=1000
                        )
                    
                    # Run simulation
                    if st.button("Run Valuation Projection", type="primary"):
                        with st.spinner("Running Monte Carlo simulation..."):
                            result = simulate_player_valuation(
                                current_value=initial_value,
                                age=player_age,
                                position=player_position,
                                months=sim_months,
                                n_paths=sim_paths,
                                seed=42
                            )
                        
                        if result:
                            # Display results
                            st.success(f"Completed {sim_paths} simulations over {sim_months} months")
                            
                            # Summary statistics table
                            st.markdown("#### Summary Statistics")
                            summary_data = []
                            for scenario, stats in result.summary.items():
                                summary_data.append({
                                    'Scenario': scenario,
                                    'Mean (€M)': f"{stats['mean']:.2f}",
                                    'Median (€M)': f"{stats['p50']:.2f}",
                                    'P10 (€M)': f"{stats['p10']:.2f}",
                                    'P90 (€M)': f"{stats['p90']:.2f}",
                                    'Prob(Down)': f"{stats['prob_down']*100:.1f}%"
                                })
                            
                            summary_df = pd.DataFrame(summary_data)
                            st.dataframe(summary_df, use_container_width=True)
                            
                            # Histogram visualization
                            st.markdown("#### Distribution of Final Valuations")
                            fig = go.Figure()
                            
                            scenarios = result.final_values['scenario'].unique()
                            colors = ['#636EFA', '#EF553B', '#00CC96']
                            
                            for i, scenario in enumerate(scenarios):
                                scenario_data = result.final_values[
                                    result.final_values['scenario'] == scenario
                                ]['V_T']
                                
                                fig.add_trace(go.Histogram(
                                    x=scenario_data,
                                    name=scenario,
                                    opacity=0.6,
                                    nbinsx=30,
                                    marker_color=colors[i % len(colors)]
                                ))
                            
                            # Add V0 reference line
                            fig.add_vline(
                                x=initial_value,
                                line_dash="dash",
                                line_color="red",
                                annotation_text=f"V₀ = €{initial_value:.2f}M",
                                annotation_position="top"
                            )
                            
                            fig.update_layout(
                                barmode='overlay',
                                xaxis_title="Final Valuation (€M)",
                                yaxis_title="Frequency",
                                height=400,
                                showlegend=True
                            )
                            
                            st.plotly_chart(fig, use_container_width=True)
                            
                            # Stratum info (collapsible)
                            with st.expander("📊 Stratum Statistics (Model Parameters)"):
                                stratum_info = result.stratum_info
                                st.markdown(f"**Stratum:** {stratum_info['age_band']}_{stratum_info['position']}")
                                
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    st.markdown("**Stay Regime**")
                                    stats_stay = stratum_info['stats_stay']
                                    st.write(f"- Sample size: {stats_stay.n}")
                                    st.write(f"- μ (30-day): {stats_stay.mu_rate_per_30day:.6f}")
                                    st.write(f"- σ (30-day): {stats_stay.sigma_rate_per_30day:.6f}")
                                    st.write(f"- Median Δt: {stats_stay.dt_days_median} days")
                                
                                with col2:
                                    st.markdown("**Move Regime**")
                                    stats_move = stratum_info['stats_move']
                                    st.write(f"- Sample size: {stats_move.n}")
                                    st.write(f"- μ (30-day): {stats_move.mu_rate_per_30day:.6f}")
                                    st.write(f"- σ (30-day): {stats_move.sigma_rate_per_30day:.6f}")
                                    st.write(f"- Median Δt: {stats_move.dt_days_median} days")
                        else:
                            st.error(f"No stratum data available for {age_band}_{pos_group}")
                            st.info("Try adjusting the player's classification or check if transition statistics exist for this stratum.")
                else:
                    st.warning("Player age or position data not available for valuation projection")
            else:
                st.info("No transfer history available for this player")
    
    elif view_mode == "Batch Valuation EDA":
        st.header("Batch Valuation Analysis")
        st.markdown("Exploratory analysis of valuation projections across all player strata")
        
        # Check for pre-computed batch results
        latest_batch_dir = get_latest_batch_results()
        
        if not latest_batch_dir:
            st.warning("No batch valuation results found.")
            st.info("Run the batch processing script first:")
            st.code("python scripts/run_batch_valuations.py")
            st.markdown("This will generate valuation projections for all strata and save them to `data/summary/`")
        else:
            # Load batch results
            batch_results_path = latest_batch_dir / "batch_results.csv"
            summary_path = latest_batch_dir / "summary.json"
            
            if not batch_results_path.exists():
                st.error(f"Results file not found: {batch_results_path}")
            else:
                # Load data
                batch_df = pd.read_csv(batch_results_path)
                
                with open(summary_path, 'r') as f:
                    summary_meta = json.load(f)
                
                # Display metadata
                st.success(f"Loaded batch results from: **{latest_batch_dir.name}**")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Strata", summary_meta['stats']['num_strata'])
                with col2:
                    st.metric("Scenarios", len(batch_df['scenario'].unique()))
                with col3:
                    st.metric("Horizon", f"{summary_meta['parameters']['months']} months")
                with col4:
                    st.metric("Simulations", f"{summary_meta['parameters']['n_paths']:,}")
                
                st.markdown("---")
                
                # Filters
                st.subheader("Filters")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    selected_age_bands = st.multiselect(
                        "Age Bands",
                        options=sorted(batch_df['age_band'].unique()),
                        default=sorted(batch_df['age_band'].unique())
                    )
                
                with col2:
                    selected_positions = st.multiselect(
                        "Positions",
                        options=sorted(batch_df['position'].unique()),
                        default=sorted(batch_df['position'].unique())
                    )
                
                with col3:
                    selected_scenarios = st.multiselect(
                        "Scenarios",
                        options=sorted(batch_df['scenario'].unique()),
                        default=sorted(batch_df['scenario'].unique())
                    )
                
                # Apply filters
                filtered_df = batch_df[
                    (batch_df['age_band'].isin(selected_age_bands)) &
                    (batch_df['position'].isin(selected_positions)) &
                    (batch_df['scenario'].isin(selected_scenarios))
                ]
                
                if filtered_df.empty:
                    st.warning("No data matches the selected filters")
                else:
                    st.info(f"Showing {len(filtered_df)} results from {len(filtered_df['stratum'].unique())} strata")
                    
                    # Summary statistics
                    st.markdown("---")
                    st.subheader("Summary Statistics by Scenario")
                    
                    scenario_summary = filtered_df.groupby('scenario').agg({
                        'mean_VT': 'mean',
                        'median_VT': 'median',
                        'p10_VT': 'mean',
                        'p90_VT': 'mean',
                        'prob_down': 'mean',
                        'stratum': 'count'
                    }).round(3)
                    
                    scenario_summary.columns = ['Mean V_T', 'Median V_T', 'Avg P10', 'Avg P90', 'Avg Prob(Down)', 'Count']
                    st.dataframe(scenario_summary, use_container_width=True)
                    
                    # Visualizations
                    st.markdown("---")
                    st.subheader("Distribution Analysis")
                    
                    # Box plot by scenario
                    st.markdown("#### Mean Final Valuation by Scenario")
                    fig_box = go.Figure()
                    
                    for scenario in selected_scenarios:
                        scenario_data = filtered_df[filtered_df['scenario'] == scenario]
                        fig_box.add_trace(go.Box(
                            y=scenario_data['mean_VT'],
                            name=scenario,
                            boxmean='sd'
                        ))
                    
                    fig_box.update_layout(
                        yaxis_title="Mean Final Valuation (€M)",
                        height=400,
                        showlegend=True
                    )
                    st.plotly_chart(fig_box, use_container_width=True)
                    
                    # Heatmap: Position x Age Band
                    st.markdown("#### Mean Return by Position and Age Band")
                    
                    scenario_for_heatmap = st.selectbox(
                        "Select scenario for heatmap",
                        options=selected_scenarios
                    )
                    
                    heatmap_data = filtered_df[filtered_df['scenario'] == scenario_for_heatmap].pivot_table(
                        values='mean_VT',
                        index='position',
                        columns='age_band',
                        aggfunc='mean'
                    )
                    
                    fig_heatmap = go.Figure(data=go.Heatmap(
                        z=heatmap_data.values,
                        x=heatmap_data.columns,
                        y=heatmap_data.index,
                        colorscale='RdYlGn',
                        text=heatmap_data.values,
                        texttemplate='%{text:.2f}',
                        textfont={"size": 12},
                        colorbar=dict(title="Mean V_T (€M)")
                    ))
                    
                    fig_heatmap.update_layout(
                        xaxis_title="Age Band",
                        yaxis_title="Position",
                        height=400
                    )
                    st.plotly_chart(fig_heatmap, use_container_width=True)
                    
                    # Risk analysis
                    st.markdown("---")
                    st.subheader("Risk Analysis")
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("#### Top 10 Highest Expected Returns")
                        top_returns = filtered_df.nlargest(10, 'mean_VT')[
                            ['stratum', 'scenario', 'mean_VT', 'prob_down']
                        ].copy()
                        top_returns['mean_VT'] = top_returns['mean_VT'].apply(lambda x: f"€{x:.2f}M")
                        top_returns['prob_down'] = top_returns['prob_down'].apply(lambda x: f"{x*100:.1f}%")
                        st.dataframe(top_returns, use_container_width=True, hide_index=True)
                    
                    with col2:
                        st.markdown("#### Top 10 Riskiest (Prob Down)")
                        top_risk = filtered_df.nlargest(10, 'prob_down')[
                            ['stratum', 'scenario', 'mean_VT', 'prob_down']
                        ].copy()
                        top_risk['mean_VT'] = top_risk['mean_VT'].apply(lambda x: f"€{x:.2f}M")
                        top_risk['prob_down'] = top_risk['prob_down'].apply(lambda x: f"{x*100:.1f}%")
                        st.dataframe(top_risk, use_container_width=True, hide_index=True)
                    
                    # Download section
                    st.markdown("---")
                    st.subheader("Export Data")
                    
                    csv_data = filtered_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Filtered Results (CSV)",
                        data=csv_data,
                        file_name=f"batch_valuations_filtered_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )


if __name__ == "__main__":
    main()

