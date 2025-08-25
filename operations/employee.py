import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, date
from gdrive.gdrive_upload import GoogleDriveUploader
from AI.api_Operation import PDFQA
from operations.sheet import SheetOperations
import tempfile
import os
import re
import locale
import json  
from dateutil.relativedelta import relativedelta


try:
    locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
except locale.Error:
    pass

@st.cache_resource
def get_sheet_operations():
    return SheetOperations()

@st.cache_data(ttl=30)
def load_sheet_data(sheet_name):
    sheet_ops = get_sheet_operations()
    return sheet_ops.carregar_dados_aba(sheet_name)

class EmployeeManager:
    def _parse_flexible_date(self, date_string: str) -> date | None:
        if not date_string or date_string.lower() == 'n/a':
            return None
        match = re.search(r'(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})|(\d{1,2} de \w+ de \d{4})|(\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2})', date_string, re.IGNORECASE)
        if not match:
            return None
        clean_date_string = match.group(0).replace('.', '/')
        formats = ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y', '%d de %B de %Y', '%Y-%m-%d']
        for fmt in formats:
            try:
                return datetime.strptime(clean_date_string, fmt).date()
            except ValueError:
                continue
        return None

    def __init__(self):
        self.sheet_ops = get_sheet_operations()
        if not self.initialize_sheets():
            st.error("Erro ao inicializar as abas da planilha.")
        self.load_data()
        self._pdf_analyzer = None
        self.nr20_config = {
            'Básico': {'reciclagem_anos': 3, 'reciclagem_horas': 4, 'inicial_horas': 8},
            'Intermediário': {'reciclagem_anos': 2, 'reciclagem_horas': 4, 'inicial_horas': 16},
            'Avançado I': {'reciclagem_anos': 2, 'reciclagem_horas': 4, 'inicial_horas': 20},
            'Avançado II': {'reciclagem_anos': 1, 'reciclagem_horas': 4, 'inicial_horas': 32}
        }
        self.nr_config = {
            'NR-35': {'inicial_horas': 8, 'reciclagem_horas': 8, 'reciclagem_anos': 2},
            'NR-10': {'inicial_horas': 40, 'reciclagem_horas': 40, 'reciclagem_anos': 2},
            'NR-18': {'inicial_horas': 8, 'reciclagem_horas': 8, 'reciclagem_anos': 1},
            'NR-06': {'inicial_horas': 3, 'reciclagem_horas': 3, 'reciclagem_anos': 10},
            'NR-6': {'inicial_horas': 3, 'reciclagem_horas': 3, 'reciclagem_anos': 3},
            'NR-12': {'inicial_horas': 8, 'reciclagem_horas': 8, 'reciclagem_anos': 5},
            'NR-34': {'inicial_horas': 8, 'reciclagem_horas': 8, 'reciclagem_anos': 1},
            'NR-33': {'reciclagem_anos': 1},
            'BRIGADA DE INCÊNDIO': {'reciclagem_anos': 1},
            'NR-11': {'reciclagem_anos': 3, 'reciclagem_horas': 16},
            'NBR-16710 RESGATE TÉCNICO': {'reciclagem_anos': 1},
            'PERMISSÃO DE TRABALHO (PT)': {'reciclagem_anos': 1}
        }
        

    @property
    def pdf_analyzer(self):
        if self._pdf_analyzer is None:
            self._pdf_analyzer = PDFQA()
        return self._pdf_analyzer

    def load_data(self):
        """Carrega todos os DataFrames e garante a existência da coluna 'status'."""
        try:
            from gdrive.config import (
                ASO_SHEET_NAME, EMPLOYEE_SHEET_NAME, 
                EMPLOYEE_DATA_SHEET_NAME, TRAINING_SHEET_NAME
            )
            
            # Carrega empresas e garante a coluna 'status'
            companies_data = self.sheet_ops.carregar_dados_aba(EMPLOYEE_SHEET_NAME)
            self.companies_df = pd.DataFrame(companies_data[1:], columns=companies_data[0]) if companies_data and len(companies_data) > 1 else pd.DataFrame()
            if not self.companies_df.empty:
                if 'status' not in self.companies_df.columns:
                    self.companies_df['status'] = 'Ativo'
                self.companies_df['status'] = self.companies_df['status'].fillna('Ativo')

            # Carrega funcionários e garante a coluna 'status'
            employees_data = self.sheet_ops.carregar_dados_aba(EMPLOYEE_DATA_SHEET_NAME)
            self.employees_df = pd.DataFrame(employees_data[1:], columns=employees_data[0]) if employees_data and len(employees_data) > 1 else pd.DataFrame()
            if not self.employees_df.empty:
                if 'status' not in self.employees_df.columns:
                    self.employees_df['status'] = 'Ativo'
                self.employees_df['status'] = self.employees_df['status'].fillna('Ativo')

            # Carrega ASOs e Treinamentos (não precisam de status)
            aso_data = self.sheet_ops.carregar_dados_aba(ASO_SHEET_NAME)
            self.aso_df = pd.DataFrame(aso_data[1:], columns=aso_data[0]) if aso_data and len(aso_data) > 1 else pd.DataFrame()
            
            training_data = self.sheet_ops.carregar_dados_aba(TRAINING_SHEET_NAME)
            self.training_df = pd.DataFrame(training_data[1:], columns=training_data[0]) if training_data and len(training_data) > 1 else pd.DataFrame()
        except Exception as e:
            st.error(f"Erro ao carregar dados: {str(e)}")
            self.companies_df, self.employees_df, self.aso_df, self.training_df = (pd.DataFrame() for _ in range(4))

    def initialize_sheets(self):
        """Inicializa as abas, garantindo a coluna 'status'."""
        try:
            from gdrive.config import (
                ASO_SHEET_NAME, EMPLOYEE_SHEET_NAME, 
                EMPLOYEE_DATA_SHEET_NAME, TRAINING_SHEET_NAME
            )
            sheets_structure = {
                EMPLOYEE_SHEET_NAME: ['id', 'nome', 'cnpj', 'status'],
                EMPLOYEE_DATA_SHEET_NAME: ['id', 'nome', 'empresa_id', 'cargo', 'data_admissao', 'status'],
                ASO_SHEET_NAME: ['id', 'funcionario_id', 'data_aso', 'vencimento', 'arquivo_id', 'riscos', 'cargo', 'tipo_aso'],
                TRAINING_SHEET_NAME: ['id', 'funcionario_id', 'data', 'vencimento', 'norma', 'modulo', 'status', 'arquivo_id', 'tipo_treinamento', 'carga_horaria']
            }
            for sheet_name, columns in sheets_structure.items():
                data = self.sheet_ops.carregar_dados_aba(sheet_name)
                if not data:
                    self.sheet_ops.criar_aba(sheet_name, columns)
                elif data and columns[0] and columns[-1] == 'status' and 'status' not in data[0]:
                    self.sheet_ops.add_column_if_not_exists(sheet_name, 'status')
            return True
        except Exception as e:
            st.error(f"Erro ao inicializar as abas: {str(e)}")
            return False

    def _set_status(self, sheet_name: str, item_id: str, status: str):
        """Função genérica para mudar o status de um item (empresa ou funcionário)."""
        success = self.sheet_ops.update_row_by_id(sheet_name, item_id, {'status': status})
        if success:
            st.cache_data.clear()
            st.cache_resource.clear()
            self.load_data()
        return success

    def archive_company(self, company_id: str):
        from gdrive.config import EMPLOYEE_SHEET_NAME
        return self._set_status(EMPLOYEE_SHEET_NAME, company_id, "Arquivado")

    def unarchive_company(self, company_id: str):
        from gdrive.config import EMPLOYEE_SHEET_NAME
        return self._set_status(EMPLOYEE_SHEET_NAME, company_id, "Ativo")

    def archive_employee(self, employee_id: str):
        from gdrive.config import EMPLOYEE_DATA_SHEET_NAME
        return self._set_status(EMPLOYEE_DATA_SHEET_NAME, employee_id, "Arquivado")

    def unarchive_employee(self, employee_id: str):
        from gdrive.config import EMPLOYEE_DATA_SHEET_NAME
        return self._set_status(EMPLOYEE_DATA_SHEET_NAME, employee_id, "Ativo")

    def get_latest_aso_by_employee(self, employee_id):
        """
        Retorna o ASO mais recente PARA CADA TIPO (Admissional, Periódico, etc.),
        prevenindo o SettingWithCopyWarning.
        """
        if self.aso_df.empty:
            return pd.DataFrame()
            
        aso_docs = self.aso_df[self.aso_df['funcionario_id'] == str(employee_id)].copy()
        if aso_docs.empty:
            return pd.DataFrame()
    
        if 'tipo_aso' not in aso_docs.columns:
            aso_docs['tipo_aso'] = 'Não Identificado'
        aso_docs['tipo_aso'] = aso_docs['tipo_aso'].fillna('Não Identificado').astype(str).str.strip()
        
        aso_docs['data_aso_dt'] = pd.to_datetime(aso_docs['data_aso'], format='%d/%m/%Y', errors='coerce')
        aso_docs.dropna(subset=['data_aso_dt'], inplace=True)
        if aso_docs.empty: return pd.DataFrame()
        
        latest_asos = aso_docs.sort_values('data_aso_dt', ascending=False).groupby('tipo_aso').head(1).copy()
        
        latest_asos['data_aso'] = latest_asos['data_aso_dt'].dt.date
        latest_asos['vencimento'] = pd.to_datetime(latest_asos['vencimento'], format='%d/%m/%Y', errors='coerce').dt.date
        latest_asos = latest_asos.drop(columns=['data_aso_dt'])
        
        return latest_asos.sort_values('data_aso', ascending=False)

    def get_all_trainings_by_employee(self, employee_id):
        """
        Retorna uma lista contendo APENAS o treinamento mais recente e relevante
        para cada norma.
        """
        if self.training_df.empty:
            return pd.DataFrame()
            
        training_docs = self.training_df[self.training_df['funcionario_id'] == str(employee_id)].copy()
        if training_docs.empty:
            return pd.DataFrame()
    
        # Limpeza e Normalização
        for col in ['norma', 'modulo', 'tipo_treinamento']:
            if col not in training_docs.columns:
                training_docs[col] = 'N/A'
            training_docs[col] = training_docs[col].fillna('N/A').astype(str).str.strip()
    
        # Converte a data para ordenação
        training_docs['data_dt'] = pd.to_datetime(training_docs['data'], format='%d/%m/%Y', errors='coerce')
        training_docs.dropna(subset=['data_dt'], inplace=True)
        if training_docs.empty: return pd.DataFrame()
    
        # Ordena e agrupa
        training_docs = training_docs.sort_values('data_dt', ascending=False)
        latest_trainings = training_docs.groupby('norma').head(1).copy()
                
        # Formatação Final
        # Agora estas modificações não gerarão mais o aviso.
        latest_trainings['data'] = latest_trainings['data_dt'].dt.date
        latest_trainings['vencimento'] = pd.to_datetime(latest_trainings['vencimento'], format='%d/%m/%Y', errors='coerce').dt.date
        
        latest_trainings = latest_trainings.drop(columns=['data_dt'])
        
        return latest_trainings.sort_values('data', ascending=False)

    def analyze_training_pdf(self, pdf_file):
        """
        Analisa um PDF de certificado de treinamento usando um prompt JSON estruturado para extrair informações.
        """
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(pdf_file.getvalue())
                temp_path = temp_file.name
            
            structured_prompt = """
            Você é um especialista em análise de documentos de Saúde e Segurança do Trabalho. Sua tarefa é analisar o certificado de treinamento em PDF e extrair as informações abaixo.

            **REGRAS OBRIGATÓRIAS:**
            1.  Responda **APENAS com um bloco de código JSON válido**. Não inclua a palavra "json" ou qualquer outro texto antes ou depois do bloco JSON.
            2.  Para a chave de data, use ESTRITAMENTE o formato **DD/MM/AAAA**.
            3.  Se uma informação não for encontrada de forma clara, o valor da chave correspondente no JSON deve ser **null** (sem aspas).
            4.  Para a chave "norma", retorne o nome padronizado (ex: 'NR-10', 'NR-35').
            5.  Para a chave "carga_horaria", retorne apenas o número inteiro de horas.
            6.  **IMPORTANTE:** Os valores das chaves no JSON **NÃO DEVEM** conter o nome da chave.
                -   **ERRADO:** `"norma": "Norma: NR-35"`
                -   **CORRETO:** `"norma": "NR-35"`

            **JSON a ser preenchido:**
            ```json
            {
            "norma": "A norma regulamentadora do treinamento (ex: 'NR-20', 'NBR 16710' 'Brigada de Incêndio', 'IT-17','NR-11', 'NR-35', Permissão de Trabalho).",
            "modulo": "O módulo específico do treinamento (ex: 'Emitente', 'Requisitante', 'Resgate Técnico Industrial', 'Operador de Empilhadeira', 'Munck', 'Guindauto','Básico', 'Avançado', 'Supervisor'). Se não for aplicável, use 'N/A', Não considere 'Nivel' apenas o módulo ex se vier 'Intermediário Nível III' considere apenas 'Intermediário'.",
            "data_realizacao": "A data de conclusão ou emissão do certificado. Formato: DD/MM/AAAA.",
            "tipo_treinamento": "Identifique se é 'formação' (inicial) ou 'reciclagem' se não estiver descrito será 'formação'.",
            "carga_horaria": "A carga horária total do treinamento, apenas o número."
            }

            """
            answer, _ = self.pdf_analyzer.answer_question([temp_path], structured_prompt)

        except Exception as e:
            st.error(f"Erro ao processar o arquivo PDF de treinamento: {str(e)}")
            return None
        finally:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)

        if not answer:
            st.error("A IA não retornou nenhuma resposta para o certificado de treinamento.")
            return None

        try:
            cleaned_answer = answer.strip().replace("```json", "").replace("```", "")
            data = json.loads(cleaned_answer)

            data_realizacao = self._parse_flexible_date(data.get('data_realizacao'))
            norma_bruta = data.get('norma')
            
            if not data_realizacao or not norma_bruta:
                st.error("Não foi possível extrair a data de realização ou a norma do certificado a partir da resposta da IA.")
                st.code(f"Resposta recebida da IA:\n{answer}")
                return None
                
            norma_padronizada = self._padronizar_norma(norma_bruta)
            carga_horaria = int(data.get('carga_horaria', 0)) if data.get('carga_horaria') is not None else 0
            modulo = data.get('modulo', "N/A")
            tipo_treinamento = str(data.get('tipo_treinamento', 'formação')).lower()
            
            if norma_padronizada == "NR-20" and (not modulo or modulo.lower() == 'n/a'):
                st.info("Módulo da NR-20 não encontrado, tentando inferir pela carga horária...")
                key_ch = 'inicial_horas' if tipo_treinamento == 'formação' else 'reciclagem_horas'
                for mod, config in self.nr20_config.items():
                    if carga_horaria == config.get(key_ch):
                        modulo = mod
                        st.success(f"Módulo inferido como '{mod}' com base na carga horária de {carga_horaria}h.")
                        break
            
            return {
                'data': data_realizacao, 
                'norma': norma_padronizada, 
                'modulo': modulo, 
                'tipo_treinamento': tipo_treinamento, 
                'carga_horaria': carga_horaria
            }

        except (json.JSONDecodeError, AttributeError, TypeError, ValueError) as e:
            st.error(f"Erro ao processar a resposta da IA para o treinamento. A resposta pode não ser um JSON válido ou os dados estão incorretos: {e}")
            st.code(f"Resposta recebida da IA:\n{answer}")
            return None

    def analyze_aso_pdf(self, pdf_file):
        """
        Analisa um PDF de ASO usando um prompt JSON estruturado para extrair informações.
        """
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_file.write(pdf_file.getvalue())
                temp_path = temp_file.name
            
            st.info("Iniciando análise do ASO com prompt estruturado...")
            
            structured_prompt = """        
            Você é um assistente de extração de dados para documentos de Saúde e Segurança do Trabalho. Sua tarefa é analisar o ASO em PDF e extrair as informações abaixo.
            REGRAS OBRIGATÓRIAS:
            1.Responda APENAS com um bloco de código JSON válido. Não inclua a palavra "json" ou qualquer outro texto antes ou depois do bloco JSON.
            2.Para todas as chaves de data, use ESTRITAMENTE o formato DD/MM/AAAA.
            3.Se uma informação não for encontrada de forma clara e inequívoca, o valor da chave correspondente no JSON deve ser null (sem aspas).
            4.IMPORTANTE: Os valores das chaves no JSON NÃO DEVEM conter o nome da chave.
            ERRADO: "cargo": "Cargo: Operador"
            CORRETO: "cargo": "Operador"
            JSON a ser preenchido:

            {
            "data_aso": "A data de emissão ou realização do exame clínico. Formato: DD/MM/AAAA.",
            "vencimento_aso": "A data de vencimento explícita no ASO, se houver. Formato: DD/MM/AAAA.",
            "riscos": "Uma string contendo os riscos ocupacionais listados, separados por vírgula.",
            "cargo": "O cargo ou função do trabalhador.",
            "tipo_aso": "O tipo de exame. Identifique como um dos seguintes: 'Admissional', 'Periódico', 'Demissional', 'Mudança de Risco', 'Retorno ao Trabalho', 'Monitoramento Pontual'."
            }

            """
            answer, _ = self.pdf_analyzer.answer_question([temp_path], structured_prompt)
        
        except Exception as e:
            st.error(f"Erro ao processar o arquivo PDF do ASO: {str(e)}")
            return None
        finally:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)

        if not answer:
            st.error("A IA não retornou nenhuma resposta para o ASO.")
            return None

        try:
            cleaned_answer = answer.strip().replace("```json", "").replace("```", "")
            data = json.loads(cleaned_answer)

            data_aso = self._parse_flexible_date(data.get('data_aso'))
            vencimento = self._parse_flexible_date(data.get('vencimento_aso'))
            
            if not data_aso:
                st.error("Não foi possível extrair a data de emissão do ASO a partir da resposta da IA.")
                st.code(f"Resposta recebida da IA:\n{answer}")
                return None
                
            tipo_aso = str(data.get('tipo_aso', 'Não identificado'))

            if not vencimento and tipo_aso != 'Demissional':
                st.info(f"Vencimento não encontrado explicitamente. Calculando com base no tipo '{tipo_aso}'...")
                if tipo_aso in ['Admissional', 'Periódico', 'Mudança de Risco', 'Retorno ao Trabalho']:
                    vencimento = data_aso + timedelta(days=365)
                elif tipo_aso == 'Monitoramento Pontual':
                    vencimento = data_aso + timedelta(days=180)
                else:
                    vencimento = data_aso + timedelta(days=365)
                    st.warning(f"Tipo de ASO '{tipo_aso}' não mapeado para cálculo de vencimento, assumindo validade de 1 ano.")
            
            return {
                'data_aso': data_aso, 
                'vencimento': vencimento, 
                'riscos': data.get('riscos', ""), 
                'cargo': data.get('cargo', ""),
                'tipo_aso': tipo_aso
            }

        except (json.JSONDecodeError, AttributeError) as e:
            st.error(f"Erro ao processar a resposta da IA para o ASO. A resposta não era um JSON válido: {e}")
            st.code(f"Resposta recebida da IA:\n{answer}")
            return None

    def add_company(self, nome, cnpj):
        from gdrive.config import EMPLOYEE_SHEET_NAME
        if not self.companies_df.empty and cnpj in self.companies_df['cnpj'].values:
            return None, "CNPJ já cadastrado."
        # Adiciona o status 'Ativo' no momento do cadastro
        new_data = [nome, cnpj, "Ativo"]
        try:
            company_id = self.sheet_ops.adc_dados_aba(EMPLOYEE_SHEET_NAME, new_data)
            if company_id:
                st.cache_resource.clear()
                self.load_data()
                return company_id, "Empresa cadastrada com sucesso"
            return None, "Falha ao obter ID da empresa."
        except Exception as e:
            return None, f"Erro ao cadastrar empresa: {str(e)}"
         
    def add_employee(self, nome, cargo, data_admissao, empresa_id):
        from gdrive.config import EMPLOYEE_DATA_SHEET_NAME
        # Adiciona o status 'Ativo' no momento do cadastro
        new_data = [nome, str(empresa_id), cargo, data_admissao.strftime("%d/%m/%Y"), "Ativo"]
        try:
            employee_id = self.sheet_ops.adc_dados_aba(EMPLOYEE_DATA_SHEET_NAME, new_data)
            if employee_id:
                st.cache_data.clear()
                self.load_data()
                return employee_id, "Funcionário adicionado com sucesso"
            return None, "Erro ao adicionar funcionário na planilha"
        except Exception as e:
            return None, f"Erro ao adicionar funcionário: {str(e)}"

    def add_aso(self, aso_data: dict):
        """
        Adiciona um novo registro de ASO à planilha a partir de um dicionário.
        Se um campo opcional não for encontrado, insere um valor padrão como "Não identificado".
        """
        from gdrive.config import ASO_SHEET_NAME
    
        # 1. Extrai os dados essenciais. Se faltarem, a função para.
        funcionario_id = aso_data.get('funcionario_id')
        data_aso = aso_data.get('data_aso')
        arquivo_id = aso_data.get('arquivo_id')
        
        if not all([funcionario_id, data_aso, arquivo_id]):
            st.error("Dados críticos para o ASO (ID do Funcionário, Data ou Arquivo) estão faltando e não puderam ser salvos.")
            return None
    
        # 2. Extrai os dados opcionais, fornecendo "Não identificado" como valor padrão.
        #    O método .get(chave, valor_padrao) é perfeito para isso.
        vencimento = aso_data.get('vencimento') # Vencimento pode ser None (ex: demissional)
        cargo = aso_data.get('cargo', 'Não identificado')
        riscos = aso_data.get('riscos', 'Não identificado')
        tipo_aso = aso_data.get('tipo_aso', 'Não identificado')
    
        # 3. Garante que mesmo que a IA retorne um valor vazio (""), nós salvemos "Não identificado".
        cargo_str = cargo if cargo else 'Não identificado'
        riscos_str = riscos if riscos else 'Não identificado'
        tipo_aso_str = tipo_aso if tipo_aso else 'Não identificado'
        vencimento_str = vencimento.strftime("%d/%m/%Y") if vencimento else "N/A"
        
        # 4. Monta a linha a ser inserida na planilha com os dados tratados.
        new_data = [
            str(funcionario_id),
            data_aso.strftime("%d/%m/%Y"),
            vencimento_str,
            str(arquivo_id),
            riscos_str,
            cargo_str,
            tipo_aso_str
        ]
        
        try:
            aso_id = self.sheet_ops.adc_dados_aba(ASO_SHEET_NAME, new_data)
            if aso_id:
                st.cache_data.clear()
                self.load_data()
                return aso_id
            return None
        except Exception as e:
            st.error(f"Erro ao adicionar ASO na planilha: {str(e)}")
            return None
        
    def _padronizar_norma(self, norma):
        if not norma:
            return None
        
        norma_upper = str(norma).strip().upper()
    

        # Regra 1: Brigada de Incêndio
        if "BRIGADA" in norma_upper or "INCÊNDIO" in norma_upper or "IT-17" in norma_upper or "IT 17" in norma_upper or "NR-23" in norma_upper or "NR 23" in norma_upper:
            return "BRIGADA DE INCÊNDIO"

        # Regra 2: NBR 16710 (Resgate Técnico)
        if "16710" in norma_upper or "RESGATE TÉCNICO" in norma_upper:
            return "NBR-16710 RESGATE TÉCNICO"
        
        if "PERMISSÃO" in norma_upper or re.search(r'\b(PT)\b', norma_upper): 
            return "PERMISSÃO DE TRABALHO (PT)"
            
        # Regra 4: NRs numéricas (ex: NR-10, NR 11, NR-06)
        match = re.search(r'NR\s?-?(\d+)', norma_upper)
        if match:
            num = int(match.group(1))
            return f"NR-{num:02d}" # Formata com zero à esquerda (ex: NR-06)
            
        return norma_upper


    def add_training(self, training_data: dict):
        """
        Adiciona um novo registro de treinamento a partir de um dicionário,
        com validação robusta e tratamento de campos opcionais.
        """
        from gdrive.config import TRAINING_SHEET_NAME
    
        # 1. Extrai os dados essenciais do dicionário.
        #    Esta função agora espera um dicionário com estas chaves.
        funcionario_id = training_data.get('funcionario_id')
        data = training_data.get('data')
        norma = training_data.get('norma')
        vencimento = training_data.get('vencimento')
        anexo = training_data.get('anexo')
        
        # 2. Valida os campos críticos. Se algum faltar, a função para com uma mensagem clara.
        if not all([funcionario_id, data, norma, vencimento, anexo]):
            missing = [k for k, v in {
                'ID do Funcionário': funcionario_id, 
                'Data': data, 
                'Norma': norma, 
                'Vencimento': vencimento, 
                'Anexo': anexo
            }.items() if not v]
            st.error(f"Não foi possível salvar o treinamento. Dados críticos faltando: {', '.join(missing)}")
            return None
    
        # 3. Extrai dados opcionais com valores padrão seguros.
        modulo = training_data.get('modulo', 'N/A')
        status = training_data.get('status', 'Válido')
        tipo_treinamento = training_data.get('tipo_treinamento', 'Não identificado')
        carga_horaria = training_data.get('carga_horaria', '0')
    
        # 4. Monta a lista de dados para a nova linha na planilha.
        new_data = [
            str(funcionario_id),
            data.strftime("%d/%m/%Y"),
            vencimento.strftime("%d/%m/%Y"),
            self._padronizar_norma(norma),
            str(modulo) if modulo else 'N/A',
            str(status),
            str(anexo),
            str(tipo_treinamento) if tipo_treinamento else 'Não identificado',
            str(carga_horaria) if carga_horaria is not None else '0'
        ]
        
        try:
            # A função adc_dados_aba gera o 'id' único do registro e o retorna.
            training_id = self.sheet_ops.adc_dados_aba(TRAINING_SHEET_NAME, new_data)
            if training_id:
                st.cache_data.clear()
                self.load_data()
                return training_id
            
            # Fallback se a função da planilha não retornar um ID.
            st.error("A escrita na planilha falhou e não retornou um ID de registro.")
            return None
        except Exception as e:
            st.error(f"Erro ao adicionar treinamento na planilha: {str(e)}")
            return None

    def get_company_name(self, company_id):
        if self.companies_df.empty:
            return None
        company = self.companies_df[self.companies_df['id'] == str(company_id)]
        return company.iloc[0]['nome'] if not company.empty else None

    def get_employee_name(self, employee_id):
        if self.employees_df.empty:
            return None
        employee = self.employees_df[self.employees_df['id'] == str(employee_id)]
        return employee.iloc[0]['nome'] if not employee.empty else None

    def get_employees_by_company(self, company_id: str, include_archived: bool = False):
        """
        Retorna os funcionários de uma empresa.
        Por padrão, retorna apenas os ativos.
        """
        if self.employees_df.empty:
            return pd.DataFrame()
        
        company_employees = self.employees_df[self.employees_df['empresa_id'] == str(company_id)]
        
        if include_archived:
            return company_employees
        else:
            return company_employees[company_employees['status'].str.lower() == 'ativo']

    def get_employee_docs(self, employee_id):
        latest_aso = self.get_latest_aso_by_employee(employee_id)
        latest_trainings = self.get_all_trainings_by_employee(employee_id)
        return latest_aso, latest_trainings

    def calcular_vencimento_treinamento(self, data, norma, modulo=None, tipo_treinamento='formação'):
        """
        Calcula o vencimento de um treinamento com uma normalização de módulo aprimorada
        para lidar com casos como "Avançado I".
        """
        if not isinstance(data, date):
            return None
            
        norma_padronizada = self._padronizar_norma(norma)
        if not norma_padronizada:
            return None
        
        config = None
        anos_validade = None
    
        if norma_padronizada == "NR-20":
            
            # 1. Verifica se o módulo foi fornecido e é uma string
            if modulo and isinstance(modulo, str):
                modulo_limpo = modulo.strip()
                
                # 2. Itera sobre as chaves do dicionário de configuração da NR-20
                for key, value in self.nr20_config.items():
                    # 3. Compara as versões em minúsculas para encontrar a correspondência
                    if key.lower() == modulo_limpo.lower():
                        config = value
                        anos_validade = config.get('reciclagem_anos')
                        break # Para o loop assim que encontra a correspondência
            
            # 4. Lógica de fallback: se, após a busca, não encontrou um 'anos_validade'
            if anos_validade is None:
                st.warning(f"Módulo da NR-20 ('{modulo}') não reconhecido. Assumindo o prazo de validade mais curto (1 ano) por segurança.")
                anos_validade = 1
    
        else:
            # Lógica para outras NRs (sem alterações)
            config = self.nr_config.get(norma_padronizada)
            if config:
                anos_validade = config.get('reciclagem_anos')
    
        # Cálculo final da data (sem alterações)
        if anos_validade is not None:
            try:
                # Tenta usar dateutil para um cálculo mais preciso
                from dateutil.relativedelta import relativedelta
                return data + relativedelta(years=int(anos_validade))
            except ImportError:
                # Fallback para o cálculo simples se a biblioteca não estiver instalada
                return data + timedelta(days=int(anos_validade * 365.25))
    
        st.error(f"Não foi possível encontrar regras de vencimento para a norma '{norma_padronizada}'.")
        return None
        
    def archive_training(self, training_id: str, archive: bool = True):
        """Marca um treinamento como arquivado ou ativo."""
        from gdrive.config import TRAINING_SHEET_NAME
        status = "Arquivado" if archive else "Ativo"
        return self.sheet_ops.update_row_by_id(
            TRAINING_SHEET_NAME, 
            training_id, 
            {'status': status}
        )

    def delete_training(self, training_id: str, file_url: str):
        """Deleta permanentemente um treinamento e seu arquivo no Drive."""
        from gdrive.config import TRAINING_SHEET_NAME
        uploader = GoogleDriveUploader()
        if file_url and pd.notna(file_url):
            if not uploader.delete_file_by_url(file_url):
                st.warning("Falha ao deletar o arquivo do Google Drive, mas prosseguindo.")
        
        return self.sheet_ops.excluir_dados_aba(TRAINING_SHEET_NAME, training_id)

    def delete_aso(self, aso_id: str, file_url: str):
        """Deleta permanentemente um ASO e seu arquivo no Drive."""
        from gdrive.config import ASO_SHEET_NAME
        uploader = GoogleDriveUploader()
        if file_url and pd.notna(file_url):
            if not uploader.delete_file_by_url(file_url):
                st.warning("Falha ao deletar o arquivo do Google Drive, mas prosseguindo.")

        return self.sheet_ops.excluir_dados_aba(ASO_SHEET_NAME, aso_id)

    def archive_all_employee_docs(self, employee_id: str):
        """Arquiva todos os treinamentos de um funcionário específico."""
        trainings_to_archive = self.training_df[self.training_df['funcionario_id'] == str(employee_id)]
        if trainings_to_archive.empty:
            st.info("Funcionário não possui treinamentos para arquivar.")
            return True

        success_count = 0
        for index, row in trainings_to_archive.iterrows():
            if self.archive_training(row['id'], archive=True):
                success_count += 1
            
        if success_count == len(trainings_to_archive):
            st.cache_data.clear()
            self.load_data()
            return True
        else:
            st.error("Alguns treinamentos não puderam ser arquivados.")
            return False

    def delete_all_employee_data(self, employee_id: str):
        """Exclui permanentemente um funcionário, seus ASOs, treinamentos e todos os arquivos associados."""
        from gdrive.config import EMPLOYEE_DATA_SHEET_NAME
        
        print(f"Iniciando exclusão total para o funcionário ID: {employee_id}")
        
        trainings_to_delete = self.training_df[self.training_df['funcionario_id'] == str(employee_id)]
        for index, row in trainings_to_delete.iterrows():
            self.delete_training(row['id'], row.get('arquivo_id'))
        
        asos_to_delete = self.aso_df[self.aso_df['funcionario_id'] == str(employee_id)]
        for index, row in asos_to_delete.iterrows():
            self.delete_aso(row['id'], row.get('arquivo_id'))
        
        if self.sheet_ops.excluir_dados_aba(EMPLOYEE_DATA_SHEET_NAME, employee_id):
            print(f"Registro do funcionário ID {employee_id} excluído da planilha.")
            st.cache_data.clear()
            self.load_data()
            return True
        else:
            st.error(f"Falha ao excluir o registro principal do funcionário ID {employee_id}.")
            return False 
    def validar_treinamento(self, norma, modulo, tipo_treinamento, carga_horaria):
        norma_padronizada = self._padronizar_norma(norma)
        
        # Lógica para NR-33
        if norma_padronizada == "NR-33":
            modulo_normalizado = ""
            if modulo:
                if "supervisor" in modulo.lower():
                    modulo_normalizado = "supervisor"
                elif "trabalhador" in modulo.lower() or "autorizado" in modulo.lower():
                    modulo_normalizado = "trabalhador"
            
            if tipo_treinamento == 'formação':
                if modulo_normalizado == "supervisor" and carga_horaria < 40:
                    return False, f"Carga horária para formação de Supervisor (NR-33) deve ser de 40h, mas foi de {carga_horaria}h."
                if modulo_normalizado == "trabalhador" and carga_horaria < 16:
                    return False, f"Carga horária para formação de Trabalhador Autorizado (NR-33) deve ser de 16h, mas foi de {carga_horaria}h."
            
            elif tipo_treinamento == 'reciclagem':
                if carga_horaria < 8:
                    return False, f"Carga horária para reciclagem (NR-33) deve ser de 8h, mas foi de {carga_horaria}h."
        
        # Lógica para Permissão de Trabalho (PT)
        elif norma_padronizada == "PERMISSÃO DE TRABALHO (PT)":
            modulo_lower = str(modulo).lower()
            if "emitente" in modulo_lower:
                if tipo_treinamento == 'formação' and carga_horaria < 16:
                    return False, f"Carga horária para formação de Emitente de PT deve ser de 16h, mas foi de {carga_horaria}h."
                elif tipo_treinamento == 'reciclagem' and carga_horaria < 4:
                    return False, f"Carga horária para reciclagem de Emitente de PT deve ser de 4h, mas foi de {carga_horaria}h."
            elif "requisitante" in modulo_lower:
                if tipo_treinamento == 'formação' and carga_horaria < 8:
                    return False, f"Carga horária para formação de Requisitante de PT deve ser de 8h, mas foi de {carga_horaria}h."
                elif tipo_treinamento == 'reciclagem' and carga_horaria < 4:
                    return False, f"Carga horária para reciclagem de Requisitante de PT deve ser de 4h, mas foi de {carga_horaria}h."
          
        # Lógica para Brigada de Incêndio
        elif norma_padronizada == "BRIGADA DE INCÊNDIO":
            is_avancado = "avançado" in str(modulo).lower()
            if is_avancado:
                if tipo_treinamento == 'formação' and carga_horaria < 24:
                    return False, f"Carga horária para formação de Brigada Avançada deve ser de 24h, mas foi de {carga_horaria}h."
                elif tipo_treinamento == 'reciclagem' and carga_horaria < 16:
                    return False, f"Carga horária para reciclagem de Brigada Avançada deve ser de 16h, mas foi de {carga_horaria}h."

        # Lógica para NR-11
        elif norma_padronizada == "NR-11":
            if tipo_treinamento == 'formação' and carga_horaria < 16:
                return False, f"Carga horária para formação (NR-11) parece baixa ({carga_horaria}h). O mínimo comum é 16h."
            elif tipo_treinamento == 'reciclagem' and carga_horaria < 16:
                 return False, f"Carga horária para reciclagem (NR-11) deve ser de 16h, mas foi de {carga_horaria}h."
        
        # Lógica para NBR 16710
        elif norma_padronizada == "NBR-16710 RESGATE TÉCNICO":
            is_industrial_rescue = "industrial" in str(modulo).lower()
            if is_industrial_rescue:
                if tipo_treinamento == 'formação' and carga_horaria < 24:
                    return False, f"Carga horária para formação de Resgate Técnico Industrial (NBR 16710) deve ser de no mínimo 24h, mas foi de {carga_horaria}h."
                elif tipo_treinamento == 'reciclagem' and carga_horaria < 24:
                    return False, f"Carga horária para reciclagem de Resgate Técnico Industrial (NBR 16710) deve ser de no mínimo 24h, mas foi de {carga_horaria}h."
        
        # Se nenhuma das condições de falha for atendida, o treinamento é considerado conforme.
        return True, "Carga horária conforme."




