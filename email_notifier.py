import os
import sys
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date, timedelta
import pandas as pd

# Adiciona o diretório raiz ao path para encontrar os módulos
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from operations.employee import EmployeeManager
from operations.company_docs import CompanyDocsManager

def get_smtp_config_from_env():
    """Lê a configuração SMTP a partir de variáveis de ambiente."""
    config = {
        "smtp_server": "smtp.gmail.com", 
        "smtp_port": 465, 
        "sender_email": os.getenv("SENDER_EMAIL"),
        "sender_password": os.getenv("SENDER_PASSWORD"),
        "receiver_email": os.getenv("RECEIVER_EMAIL")
    }
    if not all([config["sender_email"], config["sender_password"], config["receiver_email"]]):
        missing = [key for key, value in config.items() if not value and ("email" in key or "password" in key)]
        raise ValueError(f"Variáveis de ambiente de e-mail ausentes: {', '.join(missing)}. Verifique os Secrets.")
    return config

def categorize_expirations(employee_manager: EmployeeManager, docs_manager: CompanyDocsManager):
    """
    Carrega e categoriza os documentos, considerando APENAS empresas e
    funcionários com status 'Ativo'.
    """
    today = date.today()
    
    active_companies_df = employee_manager.companies_df[employee_manager.companies_df['status'].str.lower() == 'ativo']
    active_company_ids = active_companies_df['id'].tolist()
    
    active_employees_df = employee_manager.employees_df[
        (employee_manager.employees_df['status'].str.lower() == 'ativo') &
        (employee_manager.employees_df['empresa_id'].isin(active_company_ids))
    ]
    active_employee_ids = active_employees_df['id'].tolist()

    # Processamento de Treinamentos
    trainings_df = employee_manager.training_df[employee_manager.training_df['funcionario_id'].isin(active_employee_ids)].copy()
    latest_trainings = pd.DataFrame()
    if not trainings_df.empty:
        latest_trainings = trainings_df.sort_values('data', ascending=False).groupby(['funcionario_id', 'norma']).head(1)
        latest_trainings['vencimento_dt'] = latest_trainings['vencimento'].dt.date
        latest_trainings.dropna(subset=['vencimento_dt'], inplace=True)
        
    # Processamento de ASOs
    asos_df = employee_manager.aso_df[employee_manager.aso_df['funcionario_id'].isin(active_employee_ids)].copy()
    latest_asos = pd.DataFrame()
    if not asos_df.empty:
        latest_asos = asos_df.sort_values('data_aso', ascending=False).groupby(['funcionario_id', 'tipo_aso']).head(1)
        latest_asos['vencimento_dt'] = latest_asos['vencimento'].dt.date
        latest_asos.dropna(subset=['vencimento_dt'], inplace=True)

    # Processamento de Documentos da Empresa
    company_docs_df = docs_manager.docs_df[docs_manager.docs_df['empresa_id'].isin(active_company_ids)].copy()
    latest_company_docs = pd.DataFrame()
    if not company_docs_df.empty:
        latest_company_docs = company_docs_df.sort_values('data_emissao', ascending=False).groupby(['empresa_id', 'tipo_documento']).head(1)
        latest_company_docs['vencimento_dt'] = latest_company_docs['vencimento'].dt.date
        latest_company_docs.dropna(subset=['vencimento_dt'], inplace=True)

    # --- Filtros de Vencimento (com a nova categoria de 45 dias) ---
    vencidos_tr = latest_trainings[latest_trainings['vencimento_dt'] < today] if not latest_trainings.empty else pd.DataFrame()
    vence_15_tr = latest_trainings[(latest_trainings['vencimento_dt'] >= today) & (latest_trainings['vencimento_dt'] <= today + timedelta(days=15))] if not latest_trainings.empty else pd.DataFrame()
    vence_45_tr = latest_trainings[(latest_trainings['vencimento_dt'] > today + timedelta(days=15)) & (latest_trainings['vencimento_dt'] <= today + timedelta(days=45))] if not latest_trainings.empty else pd.DataFrame()
    
    vencidos_aso = latest_asos[latest_asos['vencimento_dt'] < today] if not latest_asos.empty else pd.DataFrame()
    vence_15_aso = latest_asos[(latest_asos['vencimento_dt'] >= today) & (latest_asos['vencimento_dt'] <= today + timedelta(days=15))] if not latest_asos.empty else pd.DataFrame()
    vence_45_aso = latest_asos[(latest_asos['vencimento_dt'] > today + timedelta(days=15)) & (latest_asos['vencimento_dt'] <= today + timedelta(days=45))] if not latest_asos.empty else pd.DataFrame()

    vencidos_docs = latest_company_docs[latest_company_docs['vencimento_dt'] < today] if not latest_company_docs.empty else pd.DataFrame()
    vence_30_docs = latest_company_docs[(latest_company_docs['vencimento_dt'] >= today) & (latest_company_docs['vencimento_dt'] <= today + timedelta(days=30))] if not latest_company_docs.empty else pd.DataFrame()

    # Adiciona informações de nome/empresa
    employee_id_to_name = employee_manager.employees_df.set_index('id')['nome']
    employee_id_to_company_name = employee_manager.employees_df.set_index('id')['empresa_id'].map(employee_manager.companies_df.set_index('id')['nome'])

    for df in [vencidos_tr, vence_15_tr, vence_45_tr, vencidos_aso, vence_15_aso, vence_45_aso]:
        if not df.empty:
            df.loc[:, 'nome_funcionario'] = df['funcionario_id'].map(employee_id_to_name)
            df.loc[:, 'empresa'] = df['funcionario_id'].map(employee_id_to_company_name)

    for df in [vencidos_docs, vence_30_docs]:
        if not df.empty:
            df.loc[:, 'empresa'] = df['empresa_id'].map(employee_manager.companies_df.set_index('id')['nome'])

    return {
        "Treinamentos Vencidos": vencidos_tr, 
        "Treinamentos que vencem em até 15 dias": vence_15_tr, 
        "Treinamentos que vencem entre 16 e 45 dias": vence_45_tr,
        "ASOs Vencidos": vencidos_aso, 
        "ASOs que vencem em até 15 dias": vence_15_aso, 
        "ASOs que vencem entre 16 e 45 dias": vence_45_aso,
        "Documentos da Empresa Vencidos": vencidos_docs, 
        "Documentos da Empresa que vencem nos próximos 30 dias": vence_30_docs,
    }


def format_email_body(categorized_data: dict) -> str:
    html_style = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 14px; }
        .container { max-width: 800px; margin: 20px auto; padding: 20px; background-color: #ffffff; border-radius: 8px; }
        h1 { font-size: 24px; text-align: center; }
        h2 { font-size: 18px; color: #34495e; margin-top: 35px; border-bottom: 2px solid #e0e0e0; }
        table { border-collapse: collapse; width: 100%; margin-bottom: 25px; font-size: 13px; }
        th, td { border: 1px solid #dddddd; padding: 8px 12px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
    """
    html_body = f"""
    <html><head>{html_style}</head><body><div class="container">
    <h1>Relatório de Vencimentos - SEGMA-SIS</h1>
    <p style="text-align:center;">Relatório automático gerado em {date.today().strftime('%d/%m/%Y')}</p>
    """
    has_content = False
    report_configs = {
        "Documentos da Empresa Vencidos": {"cols": ['empresa', 'tipo_documento', 'vencimento']},
        "Documentos da Empresa que vencem nos próximos 30 dias": {"cols": ['empresa', 'tipo_documento', 'vencimento']},
        "Treinamentos Vencidos": {"cols": ['empresa', 'nome_funcionario', 'norma', 'vencimento']},
        "ASOs Vencidos": {"cols": ['empresa', 'nome_funcionario', 'tipo_aso', 'vencimento']},
        "Treinamentos que vencem em até 15 dias": {"cols": ['empresa', 'nome_funcionario', 'norma', 'vencimento']},
        "ASOs que vencem em até 15 dias": {"cols": ['empresa', 'nome_funcionario', 'tipo_aso', 'vencimento']},
    }
    
    for title, data_df in categorized_data.items():
        if not data_df.empty:
            has_content = True
            config = report_configs.get(title, {})
            html_body += f'<h2>{title} ({len(data_df)})</h2>'
            cols_to_show = [col for col in config.get("cols", data_df.columns) if col in data_df.columns]
            df_display = data_df[cols_to_show]
            html_body += df_display.to_html(index=False, border=0, na_rep='N/A')
            
    if not has_content:
        html_body += "<h2>Nenhuma pendência encontrada!</h2><p>Todos os documentos estão em dia.</p>"
    html_body += "</div></body></html>"
    return html_body

def send_smtp_email(html_body: str, config: dict):
    message = MIMEMultipart("alternative")
    message["Subject"] = f"Alerta de Vencimentos - SEGMA-SIS - {date.today().strftime('%d/%m/%Y')}"
    message["From"] = config["sender_email"]
    message["To"] = config["receiver_email"]
    message.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    try:
        print(f"Conectando ao servidor SMTP {config['smtp_server']}...")
        with smtplib.SMTP_SSL(config["smtp_server"], config["smtp_port"], context=context) as server:
            print("Fazendo login...")
            server.login(config["sender_email"], config["sender_password"])
            print(f"Enviando e-mail para {config['receiver_email']}...")
            server.sendmail(config["sender_email"], config["receiver_email"].split(','), message.as_string())
            print("E-mail enviado com sucesso!")
    except Exception as e:
        print(f"Falha ao enviar e-mail via SMTP: {e}")
        raise

def main():
    """Função principal do script para um ambiente single-tenant."""
    print("Iniciando script de notificação de vencimentos (modo single-tenant)...")
    try:
        config = get_smtp_config_from_env()
        
        # Instancia os managers sem argumentos, como na arquitetura single-tenant
        employee_manager = EmployeeManager()
        docs_manager = CompanyDocsManager()
        
        categorized_data = categorize_expirations(employee_manager, docs_manager)

        if not any(not df.empty for df in categorized_data.values()):
            print("Nenhuma pendência encontrada para entidades ativas. E-mail não será enviado.")
        else:
            print("Pendências encontradas, gerando e-mail.")
            email_body = format_email_body(categorized_data)
            send_smtp_email(email_body, config)
        
        print("Script finalizado com sucesso.")

    except Exception as e:
        print(f"Erro fatal no script: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
