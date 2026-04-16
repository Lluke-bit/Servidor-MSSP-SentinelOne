# S1 MSSP Pro Automation - Relatório de Consumo
# Autor: Lucas Borges
# Versão: 2.3 

import os
import csv
import requests
from dotenv import load_dotenv


class S1MSSPPro:
    def __init__(self):
        load_dotenv()

        # ✅ CORRIGIDO: os.getenv() recebe o NOME da variável de ambiente, não o valor
        self.base_url = os.getenv("S1_BASE_URL", "").rstrip("/")
        self.api_token = os.getenv("S1_API_TOKEN", "")

        if not self.base_url or not self.api_token:
            raise ValueError(
                "S1_BASE_URL e S1_API_TOKEN devem estar definidos no arquivo .env\n"
                "Exemplo:\n"
                "  S1_BASE_URL=https://usea1-clmx.sentinelone.net\n"
                "  S1_API_TOKEN=seu_token_aqui"
            )

        self.headers = {
            "Authorization": f"ApiToken {self.api_token}",
            "Content-Type": "application/json",
        }
        print(f"[INFO] Conectado à API SentinelOne v2.1: {self.base_url}")

    def _get_paginated(self, endpoint, params=None):
        """Faz GET paginado, consumindo todos os cursores automaticamente."""
        results = []
        cursor = None

        while True:
            current_params = (params or {}).copy()
            if cursor:
                current_params["cursor"] = cursor

            url = f"{self.base_url}/web/api/v2.1/{endpoint}"
            response = requests.get(url, headers=self.headers, params=current_params, timeout=30)

            if response.status_code != 200:
                print(f"[ERRO] Endpoint '{endpoint}' retornou {response.status_code}: {response.text[:200]}")
                break

            data = response.json()
            results.extend(data.get("data", []))
            cursor = data.get("pagination", {}).get("nextCursor")

            if not cursor:
                break

        return results

    def _get_single(self, endpoint, params=None):
        """Faz GET simples (sem paginação) e retorna o objeto data."""
        url = f"{self.base_url}/web/api/v2.1/{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            if response.status_code == 200:
                return response.json().get("data", {})
        except requests.RequestException as e:
            print(f"[AVISO] Falha ao chamar '{endpoint}': {e}")
        return {}

    def get_accounts(self):
        print("[INFO] Coletando Accounts (Tenants)...")
        return self._get_paginated("accounts")

    def get_sites(self, account_id):
        """
        O endpoint /sites tem estrutura diferente dos demais:
        { "data": { "sites": [...], "allSites": {...} }, "pagination": {...} }
        Por isso precisa de tratamento próprio em vez de _get_paginated genérico.
        """
        results = []
        cursor = None

        while True:
            params = {"accountIds": account_id, "state": "active"}
            if cursor:
                params["cursor"] = cursor

            url = f"{self.base_url}/web/api/v2.1/sites"
            response = requests.get(url, headers=self.headers, params=params, timeout=30)

            if response.status_code != 200:
                print(f"[ERRO] /sites retornou {response.status_code}: {response.text[:200]}")
                break

            body = response.json()
            # ✅ A lista real fica em data["sites"], não direto em data
            sites_list = body.get("data", {}).get("sites", [])
            results.extend(sites_list)

            cursor = body.get("pagination", {}).get("nextCursor")
            if not cursor:
                break

        return results

   def get_agent_count(self, site_id, machine_types=None, sku=None):
    params = {
        "siteIds": site_id,
        "isDecommissioned": False  # ✅ boolean correto
    }

    if machine_types:
        params["machineTypes"] = ",".join(machine_types)

    # ⚠️ só adiciona SKU se tiver certeza
    if sku:
        params["sku"] = sku

    data = self._get_single("agents/count", params=params)

    # DEBUG pesado (pra entender pq vem vazio)
    if not data:
        print(f"[DEBUG] agents/count vazio | params={params}")

    return data.get("total", 0) if data else 0

    def check_additional_services(self, site_id):
        """Verifica serviços adicionais ativos no site."""
        services = {"Vulnerability": "Não", "CloudFunnel": "Não", "Vigilance": "Não"}

        # Vulnerability Management
        v_data = self._get_single("application-management/settings", {"siteIds": site_id})
        if v_data:
            services["Vulnerability"] = "Sim"

        # Cloud Funnel
        cf_data = self._get_single("cloud-funnel/rules", {"siteIds": site_id})
        if cf_data:
            services["CloudFunnel"] = "Sim"

        # Vigilance MDR — verifica via licença da account (campo features)
        # Ajuste conforme disponibilidade na sua conta MSSP
        # services["Vigilance"] = "Sim"  # descomentar se tiver acesso ao endpoint

        return services

    def run(self):
        accounts = self.get_accounts()

        if not accounts:
            print("[AVISO] Nenhuma Account encontrada. Verifique as permissões do token.")
            return

        report_rows = []

        for acc in accounts:
            acc_id = acc.get("id")
            acc_name = acc.get("name", "N/A")
            print(f"\n[PROCESSANDO] Account: {acc_name} (ID: {acc_id})")

            sites = self.get_sites(acc_id)

            if not sites:
                print(f"  [AVISO] Nenhum site ativo encontrado para {acc_name}")
                continue

            for site in sites:
                site_id = site.get("id")
                site_name = site.get("name", "N/A")
                print(f"  > Site: {site_name} (ID: {site_id})")

                # Contagem granular por tipo de máquina + SKU
                w_complete = self.get_agent_count(site_id, ["laptop", "desktop"], sku="complete")
                w_control  = self.get_agent_count(site_id, ["laptop", "desktop"], sku="control")
                s_complete = self.get_agent_count(site_id, ["server"], sku="complete")
                s_control  = self.get_agent_count(site_id, ["server"], sku="control")

                extras = self.check_additional_services(site_id)

                report_rows.append({
                    "PAIS":                         acc.get("country", "BR"),
                    "REVENDA":                      "Sua Revenda",  # Customizar ou extrair de tags
                    "CLIENTE":                      site_name,
                    "TENANT":                       acc_name,
                    "ACCOUNT_MANAGER":              "N/A",
                    "Complete_Workstations":        w_complete,
                    "Complete_Servers":             s_complete,
                    "Control_Workstations":         w_control,
                    "Control_Servers":              s_control,
                    "Complete_Purple_Workstations": 0,
                    "Complete_Purple_Servers":      0,
                    "Vigilance_MDR":                extras["Vigilance"],
                    "Cloud_Funnel":                 extras["CloudFunnel"],
                    "Vulnerability_Management":     extras["Vulnerability"],
                })

        # Exportar CSV
        output_file = "mssp_consumption_pro.csv"
        if report_rows:
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=report_rows[0].keys())
                writer.writeheader()
                writer.writerows(report_rows)
            print(f"\n[SUCESSO] Relatório gerado: {output_file} ({len(report_rows)} linhas)")
        else:
            print("[AVISO] Nenhum dado coletado para o relatório.")


if __name__ == "__main__":
    try:
        app = S1MSSPPro()
        app.run()
    except ValueError as e:
        print(f"[ERRO DE CONFIGURAÇÃO] {e}")
    except Exception as e:
        print(f"[ERRO CRÍTICO] {e}")
        raise
