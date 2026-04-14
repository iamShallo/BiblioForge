"""Sales history view for BiblioForge."""

import streamlit as st
from datetime import datetime, timedelta
from io import BytesIO
import pandas as pd
from biblioforge.repositories.sold_book_repository import SoldBookRepository
from pathlib import Path


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Vendite")
    return buffer.getvalue()


def _compute_metrics(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {
            "sales_count": 0.0,
            "total_quantity": 0.0,
            "avg_price": 0.0,
            "total_sales": 0.0,
        }
    return {
        "sales_count": float(len(frame)),
        "total_quantity": float(frame["Quantità"].sum()),
        "avg_price": float(frame["Prezzo Unitario"].mean()),
        "total_sales": float(frame["Totale"].sum()),
    }


def _format_delta(current: float, baseline: float) -> str | None:
    if baseline == 0:
        if current == 0:
            return "0.0%"
        return "+100.0%"
    if baseline < 0:
        return None
    change_pct = ((current - baseline) / baseline) * 100.0
    return f"{change_pct:+.1f}%"


def _compute_delta_map(active_quick_range: str, full_df: pd.DataFrame, filtered_df: pd.DataFrame) -> dict:
    delta_map = {
        "sales_count": None,
        "total_quantity": None,
        "avg_price": None,
        "total_sales": None,
    }

    if filtered_df.empty:
        return delta_map

    reference_dt = filtered_df["Data Vendita"].max()
    current_metrics = _compute_metrics(filtered_df)

    if active_quick_range == "mese":
        prev_month_date = reference_dt.to_pydatetime().replace(day=1) - timedelta(days=1)
        prev_month = prev_month_date.month
        prev_year = prev_month_date.year
        baseline_df = full_df[
            (full_df["Data Vendita"].dt.year == prev_year)
            & (full_df["Data Vendita"].dt.month == prev_month)
        ]
        baseline_metrics = _compute_metrics(baseline_df)
    elif active_quick_range == "anno":
        prev_year = int(reference_dt.year) - 1
        baseline_df = full_df[full_df["Data Vendita"].dt.year == prev_year]
        baseline_metrics = _compute_metrics(baseline_df)
    elif active_quick_range == "oggi":
        ref_year = int(reference_dt.year)
        ref_month = int(reference_dt.month)
        ref_day = int(reference_dt.day)
        month_df = full_df[
            (full_df["Data Vendita"].dt.year == ref_year)
            & (full_df["Data Vendita"].dt.month == ref_month)
        ]
        elapsed_days = max(ref_day, 1)
        month_metrics = _compute_metrics(month_df)
        baseline_metrics = {
            "sales_count": month_metrics["sales_count"] / elapsed_days,
            "total_quantity": month_metrics["total_quantity"] / elapsed_days,
            "avg_price": month_metrics["avg_price"],
            "total_sales": month_metrics["total_sales"] / elapsed_days,
        }
    else:
        return delta_map

    for key in delta_map:
        delta_map[key] = _format_delta(current_metrics[key], baseline_metrics.get(key, 0.0))

    return delta_map


def _set_quick_range(range_key: str, today, min_date, max_date) -> None:
    if range_key == "oggi":
        st.session_state["sales_start_date"] = today
        st.session_state["sales_end_date"] = today
    elif range_key == "mese":
        st.session_state["sales_start_date"] = today.replace(day=1)
        st.session_state["sales_end_date"] = today
    elif range_key == "anno":
        st.session_state["sales_start_date"] = today.replace(month=1, day=1)
        st.session_state["sales_end_date"] = today
    else:
        st.session_state["sales_start_date"] = min_date
        st.session_state["sales_end_date"] = max_date

    st.session_state["sales_quick_range"] = range_key
    st.session_state["sales_filtered"] = True


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

    today = datetime.now().date()
    min_date = df["Data Vendita"].min().date() if not df.empty else today - timedelta(days=30)
    max_date = df["Data Vendita"].max().date() if not df.empty else today

    if "sales_start_date" not in st.session_state:
        st.session_state["sales_start_date"] = min_date
    if "sales_end_date" not in st.session_state:
        st.session_state["sales_end_date"] = max_date
    if "sales_quick_range" not in st.session_state:
        st.session_state["sales_quick_range"] = "totale"

    active_quick_range = st.session_state.get("sales_quick_range", "totale")

    st.markdown("### Range Rapido")
    quick_col1, quick_col2, quick_col3, quick_col4 = st.columns(4)
    quick_col1.button(
        "Vendite di Oggi",
        key="sales-quick-today",
        use_container_width=True,
        type="primary" if active_quick_range == "oggi" else "secondary",
        on_click=_set_quick_range,
        args=("oggi", today, min_date, max_date),
    )
    quick_col2.button(
        "Vendite del Mese",
        key="sales-quick-month",
        use_container_width=True,
        type="primary" if active_quick_range == "mese" else "secondary",
        on_click=_set_quick_range,
        args=("mese", today, min_date, max_date),
    )
    quick_col3.button(
        "Vendite dell'Anno",
        key="sales-quick-year",
        use_container_width=True,
        type="primary" if active_quick_range == "anno" else "secondary",
        on_click=_set_quick_range,
        args=("anno", today, min_date, max_date),
    )
    quick_col4.button(
        "Vendite Totali",
        key="sales-quick-total",
        use_container_width=True,
        type="primary" if active_quick_range == "totale" else "secondary",
        on_click=_set_quick_range,
        args=("totale", today, min_date, max_date),
    )

    st.markdown("### Filtri")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        start_date = st.date_input(
            "Data inizio",
            value=st.session_state["sales_start_date"],
            key="sales_start_date"
        )
    
    with col2:
        end_date = st.date_input(
            "Data fine",
            value=st.session_state["sales_end_date"],
            key="sales_end_date"
        )
    
    with col3:
        st.write("")  # spacing
        st.write("")  # spacing
        filter_button = st.button("Filtra", use_container_width=True)

    if filter_button:
        st.session_state["sales_quick_range"] = "custom"

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
            delta_map = _compute_delta_map(
                st.session_state.get("sales_quick_range", "totale"),
                df,
                filtered_df,
            )
            
            stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
            
            with stat_col1:
                st.metric(
                    "Numero Vendite",
                    len(filtered_df),
                    delta=delta_map["sales_count"],
                    delta_color="normal",
                )
            
            with stat_col2:
                total_quantity = filtered_df["Quantità"].sum()
                st.metric(
                    "Quantità Totale",
                    int(total_quantity),
                    delta=delta_map["total_quantity"],
                    delta_color="normal",
                )
            
            with stat_col3:
                avg_price = filtered_df["Prezzo Unitario"].mean()
                st.metric(
                    "Prezzo Medio",
                    f"EUR {avg_price:.2f}",
                    delta=delta_map["avg_price"],
                    delta_color="normal",
                )
            
            with stat_col4:
                total_sales = filtered_df["Totale"].sum()
                st.metric(
                    "Vendita Totale",
                    f"EUR {total_sales:.2f}",
                    delta=delta_map["total_sales"],
                    delta_color="normal",
                )
            
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
            excel_data = _to_excel_bytes(display_df)
            st.download_button(
                label="Scarica Excel",
                data=excel_data,
                file_name=f"vendite_{start_date}_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
        excel_data = _to_excel_bytes(display_df)
        st.download_button(
            label="Scarica Excel",
            data=excel_data,
            file_name="vendite_tutte.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.markdown("[Torna alla dashboard](?view=dashboard)")
