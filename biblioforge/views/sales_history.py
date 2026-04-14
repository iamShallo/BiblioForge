"""Sales history view for BiblioForge."""

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
from biblioforge.repositories.sold_book_repository import SoldBookRepository
from pathlib import Path


def render_sales_history_screen():
    """Render the sales history page with filters and analytics."""
    st.markdown("## Cronologia Vendite")
    st.caption("Visualizza e filtra tutte le vendite registrate.")

    # Initialize sold_book_repo
    sold_book_repo = SoldBookRepository(
        Path(__file__).parent.parent / "data" / "processed" / "sold_books.json"
    )

    # Get all sold books
    all_sold_books = sold_book_repo.list_all()

    if not all_sold_books:
        st.info("Nessuna vendita registrata.")
        st.markdown("[Torna alla dashboard](?view=dashboard)")
        return

    # Convert to dataframe
    sales_data = []
    for sb in all_sold_books:
        sales_data.append({
            "Data Vendita": sb.sale_date,
            "Titolo": sb.normalized_title or sb.raw_title,
            "Autore": sb.author or "Autore sconosciuto",
            "Quantità": sb.quantity,
            "Prezzo Unitario": sb.price or 0.0,
            "Totale": (sb.price or 0.0) * sb.quantity,
            "ISBN": sb.isbn or "-",
            "EAN": sb.ean or "-",
        })

    df = pd.DataFrame(sales_data)
    
    # Parse dates
    df["Data Vendita"] = pd.to_datetime(df["Data Vendita"], errors="coerce")
    df = df.dropna(subset=["Data Vendita"])
    df = df.sort_values("Data Vendita", ascending=False)

    st.markdown("### Filtri")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        start_date = st.date_input(
            "Data inizio",
            value=df["Data Vendita"].min().date() if not df.empty else datetime.now().date() - timedelta(days=30),
            key="sales_start_date"
        )
    
    with col2:
        end_date = st.date_input(
            "Data fine",
            value=df["Data Vendita"].max().date() if not df.empty else datetime.now().date(),
            key="sales_end_date"
        )
    
    with col3:
        st.write("")  # spacing
        st.write("")  # spacing
        filter_button = st.button("Filtra", use_container_width=True)

    # Filter by date range
    if filter_button or "sales_filtered" in st.session_state:
        st.session_state["sales_filtered"] = True
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date).replace(hour=23, minute=59, second=59)
        
        filtered_df = df[(df["Data Vendita"] >= start_dt) & (df["Data Vendita"] <= end_dt)].copy()
        
        if filtered_df.empty:
            st.warning("Nessuna vendita trovata nel range di date selezionato.")
        else:
            # Display statistics
            st.markdown("### Statistiche")
            
            stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
            
            with stat_col1:
                st.metric("Numero Vendite", len(filtered_df))
            
            with stat_col2:
                total_quantity = filtered_df["Quantità"].sum()
                st.metric("Quantità Totale", int(total_quantity))
            
            with stat_col3:
                avg_price = filtered_df["Prezzo Unitario"].mean()
                st.metric("Prezzo Medio", f"EUR {avg_price:.2f}")
            
            with stat_col4:
                total_sales = filtered_df["Totale"].sum()
                st.metric("Vendita Totale", f"EUR {total_sales:.2f}", delta=f"EUR {total_sales:.2f}", delta_color="off")
            
            # Display filtered sales
            st.markdown("### Dettaglio Vendite")
            
            # Format display dataframe
            display_df = filtered_df.copy()
            display_df["Data Vendita"] = display_df["Data Vendita"].dt.strftime("%Y-%m-%d %H:%M:%S")
            display_df["Prezzo Unitario"] = display_df["Prezzo Unitario"].apply(lambda x: f"EUR {x:.2f}")
            display_df["Totale"] = display_df["Totale"].apply(lambda x: f"EUR {x:.2f}")
            
            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Data Vendita": st.column_config.TextColumn("Data Vendita", width="medium"),
                    "Titolo": st.column_config.TextColumn("Titolo", width="large"),
                    "Autore": st.column_config.TextColumn("Autore", width="medium"),
                    "Quantità": st.column_config.NumberColumn("Quantità", width="small"),
                    "Prezzo Unitario": st.column_config.TextColumn("Prezzo Unitario", width="small"),
                    "Totale": st.column_config.TextColumn("Totale", width="small"),
                    "ISBN": st.column_config.TextColumn("ISBN", width="small"),
                    "EAN": st.column_config.TextColumn("EAN", width="small"),
                }
            )
            
            # Export option
            csv = display_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Scarica CSV",
                data=csv,
                file_name=f"vendite_{start_date}_{end_date}.csv",
                mime="text/csv",
            )
    else:
        # Show all sales by default
        st.markdown("### Tutte le Vendite")
        
        stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
        
        with stat_col1:
            st.metric("Numero Vendite", len(df))
        
        with stat_col2:
            total_quantity = df["Quantità"].sum()
            st.metric("Quantità Totale", int(total_quantity))
        
        with stat_col3:
            avg_price = df["Prezzo Unitario"].mean()
            st.metric("Prezzo Medio", f"EUR {avg_price:.2f}")
        
        with stat_col4:
            total_sales = df["Totale"].sum()
            st.metric("Vendita Totale", f"EUR {total_sales:.2f}", delta=f"EUR {total_sales:.2f}", delta_color="off")
        
        # Format display dataframe
        display_df = df.copy()
        display_df["Data Vendita"] = display_df["Data Vendita"].dt.strftime("%Y-%m-%d %H:%M:%S")
        display_df["Prezzo Unitario"] = display_df["Prezzo Unitario"].apply(lambda x: f"EUR {x:.2f}")
        display_df["Totale"] = display_df["Totale"].apply(lambda x: f"EUR {x:.2f}")
        
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Data Vendita": st.column_config.TextColumn("Data Vendita", width="medium"),
                "Titolo": st.column_config.TextColumn("Titolo", width="large"),
                "Autore": st.column_config.TextColumn("Autore", width="medium"),
                "Quantità": st.column_config.NumberColumn("Quantità", width="small"),
                "Prezzo Unitario": st.column_config.TextColumn("Prezzo Unitario", width="small"),
                "Totale": st.column_config.TextColumn("Totale", width="small"),
                "ISBN": st.column_config.TextColumn("ISBN", width="small"),
                "EAN": st.column_config.TextColumn("EAN", width="small"),
            }
        )
        
        # Export option
        csv = display_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Scarica CSV",
            data=csv,
            file_name=f"vendite_tutte.csv",
            mime="text/csv",
        )

    st.markdown("[Torna alla dashboard](?view=dashboard)")
