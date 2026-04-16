S1 MSSP Pro Automation - Relatório de Consumo

Autor: Lucas Borges
Data: 16 de Abril de 2026
Versão: 2.0 (Baseada na API v2.1)

Descrição:
Este script automatiza a extração de dados de licenciamento e consumo da SentinelOne
para preenchimento da planilha MSSP. Ele utiliza os endpoints de 'Accounts' e 'Sites'
para mapear a hierarquia e o endpoint 'Agents/Count' para obter totais precisos de
Workstations e Servers por nível de licença (Complete, Control, etc.).

Funcionalidades:
- Mapeamento automático de Tenants (Accounts) e Clientes (Sites).
- Contagem granular de agentes por machineType (Workstation vs Server).
- Identificação de serviços adicionais (Vigilance, Vulnerability, Cloud Funnel).
- Saída em CSV compatível com a planilha de consumo.
"""

import os
import csv
import requests
import json
from dotenv import load_dotenv

class S1MSSPPro:
    def __init__(self):
        load_dotenv()
        self.base_url = os.getenv("https://usea1-clmx.sentinelone.net").rstrip('/')
        self.api_token = os.getenv("eyJraWQiOiJ1cy1lYXN0LTEtcHJvZC0wIiwiYWxnIjoiRVMyNTYifQ.eyJzdWIiOiJsdWNhcy5ib3JnZXNAY2xtLnRlY2giLCJpc3MiOiJhdXRobi11cy1lYXN0LTEtcHJvZCIsImRlcGxveW1lbnRfaWQiOiIxMjE0MjgiLCJ0eXBlIjoidXNlciIsImV4cCI6MTc3ODk0MzU4NSwiaWF0IjoxNzc2MzUxNTg1LCJqdGkiOiI3ZTRjZmJhZC00OWUwLTRlMjAtODI2Zi1jYTNkYmUzMmYzOTUifQ.fZ9QMi8v0H8zlCehnn2MuMxnUlg5qOPnDmyKsw2Kavx9yi9ly9--JCKrifKN___ls7L16e_zDE7rMK-uPKi73A")

        if not self.base_url or not self.api_token:
            raise ValueError("S1_BASE_URL e S1_API_TOKEN devem estar no seu arquivo .env")

        self.headers = {
            "Authorization": f"ApiToken {self.api_token}",
            "Content-Type": "application/json"
        }
        print(f"[INFO] Conectado à API SentinelOne v2.1: {self.base_url}")

    def _get_paginated(self, endpoint, params=None):
        results = []
        cursor = None
        while True:
            current_params = params.copy() if params else {}
            if cursor:
                current_params["cursor"] = cursor
            
            response = requests.get(f"{self.base_url}/{endpoint}", headers=self.headers, params=current_params)
            if response.status_code != 200:
                print(f"[ERRO] Falha no endpoint {endpoint}: {response.status_code} - {response.text}")
                break
            
            data = response.json()
            results.extend(data.get("data", []))
            cursor = data.get("pagination", {}).get("nextCursor")
            if not cursor:
                break
        return results

    def get_accounts(self):
        """Lista todas as Accounts (Tenants)."""
        print("[INFO] Coletando lista de Accounts...")
        return self._get_paginated("accounts")

    def get_sites(self, account_id):
        """Lista todos os Sites de uma Account específica."""
        return self._get_paginated("sites", params={"accountIds": account_id, "state": "active"})

    def get_agent_count(self, site_id, machine_types=None, sku=None):
        """
        Usa o endpoint /agents/count para obter o total de agentes filtrados.
        machine_types: ['laptop', 'desktop'] para Workstations, ['server'] para Servers.
        """
        params = {"siteIds": site_id, "isDecommissioned": False}
        if machine_types:
            params["machineTypes"] = ",".join(machine_types)
        
        # Nota: A filtragem por SKU no count pode variar. 
        # Se o count direto por SKU não for suportado, o script precisará de ajuste.
        if sku:
            params["sku"] = sku 

        response = requests.get(f"{self.base_url}/agents/count", headers=self.headers, params=params)
        if response.status_code == 200:
            return response.json().get("data", {}).get("total", 0)
        return 0

    def check_additional_services(self, site_id):
    #Verifica se serviços como Vulnerability ou Cloud Funnel estão ativos no site.
        services = {"Vulnerability": "Não", "CloudFunnel": "Não", "Vigilance": "Não"}
        
        # Verifica Vulnerability Management (Endpoint de configurações de App Management)
        v_resp = requests.get(f"{self.base_url}/application-management/settings", headers=self.headers, params={"siteIds": site_id})
        if v_resp.status_code == 200 and v_resp.json().get("data"):
            services["Vulnerability"] = "Sim"

        # Verifica Cloud Funnel
        cf_resp = requests.get(f"{self.base_url}/cloud-funnel/rules", headers=self.headers, params={"siteIds": site_id})
        if cf_resp.status_code == 200 and cf_resp.json().get("data"):
            services["CloudFunnel"] = "Sim"

        return services

    def run(self):
        accounts = self.get_accounts()
        report_rows = []

        for acc in accounts:
            acc_id = acc.get("id")
            acc_name = acc.get("name")
            print(f"[PROCESSANDO] Account: {acc_name}")

            sites = self.get_sites(acc_id)
            for site in sites:
                site_id = site.get("id")
                site_name = site.get("name")
                print(f"  > Site: {site_name}")

                # Coleta contagens granulares
                # Workstations (laptop, desktop)
                w_complete = self.get_agent_count(site_id, ["laptop", "desktop"], sku="complete")
                w_control = self.get_agent_count(site_id, ["laptop", "desktop"], sku="control")
                
                # Servers
                s_complete = self.get_agent_count(site_id, ["server"], sku="complete")
                s_control = self.get_agent_count(site_id, ["server"], sku="control")

                # Serviços extras
                extras = self.check_additional_services(site_id)

                row = {
                    "PAIS": acc.get("country", "BR"),
                    "REVENDA": "Sua Revenda", # Pode ser customizado ou extraído de tags
                    "CLIENTE": site_name,
                    "TENANT": acc_name,
                    "ACCOUNT MANAGER": "N/A",
                    "Complete_Workstations": w_complete,
                    "Complete_Servers": s_complete,
                    "Control_Workstations": w_control,
                    "Control_Servers": s_control,
                    "Complete_Purple_Workstations": 0, # Reservado para expansão
                    "Complete_Purple_Servers": 0,
                    "Vigilance_MDR": extras["Vigilance"],
                    "CLOUD_FUNNEL": extras["CloudFunnel"],
                    "Vulnerability_Management": extras["Vulnerability"]
                }
                report_rows.append(row)

        # Exportar para CSV
        output_file = "mssp_consumption_pro.csv"
        if report_rows:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=report_rows[0].keys())
                writer.writeheader()
                writer.writerows(report_rows)
            print(f"\n[SUCESSO] Relatório profissional gerado: {output_file}")
        else:
            print("[AVISO] Nenhum dado coletado para o relatório.")

if __name__ == "__main__":
    try:
        app = S1MSSPPro()
        app.run()
    except Exception as e:
        print(f"[ERRO CRÍTICO] {e}")
