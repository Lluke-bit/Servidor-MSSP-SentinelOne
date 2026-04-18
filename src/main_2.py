# S1 MSSP Pro Automation - Relatório de Consumo
# Autor: Lucas Borges
# Versão: 3.0 (Arquitetura Final)
#
# Estratégia:
#   - /accounts  → lista tenants (name)
#   - /sites     → lista sites (activeLicenses, sku, licenses.bundles→features, licenses.modules)
#   - /agents    → lista agentes por site, agrega machineType localmente
#
# Motivo de NÃO usar /agents/count:
#   Inconsistente em ambientes MSSP — filtros por sku/machineType retornam vazio
#   dependendo do tenant. A agregação local via /agents é mais confiável.

import os
import csv
import requests
from dotenv import load_dotenv


class S1MSSPPro:

    # =========================================================================
    # INIT
    # =========================================================================

    def __init__(self):
        load_dotenv()
        self.base_url = os.getenv("S1_BASE_URL_MSSP_008", "").rstrip("/")
        self.api_token = os.getenv("S1_API_TOKEN_MSSP_008", "")

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

    # =========================================================================
    # MÉTODOS DE REQUISIÇÃO BASE
    # =========================================================================

    def _get_paginated(self, endpoint, params=None):
        """
        GET paginado genérico via cursor.
        Funciona para /accounts e /agents (data é array direto).
        """
        results = []
        cursor = None

        while True:
            current_params = (params or {}).copy()
            if cursor:
                current_params["cursor"] = cursor

            url = f"{self.base_url}/web/api/v2.1/{endpoint}"
            resp = requests.get(url, headers=self.headers, params=current_params, timeout=30)

            if resp.status_code != 200:
                print(f"[ERRO] /{endpoint} → {resp.status_code}: {resp.text[:300]}")
                break

            body = resp.json()
            results.extend(body.get("data", []))
            cursor = body.get("pagination", {}).get("nextCursor")
            if not cursor:
                break

        return results

    def _get_sites_paginated(self, account_id):
        """
        GET paginado específico para /sites.
        O endpoint tem estrutura aninhada:
          { data: { sites: [...], allSites: {...} }, pagination: {...} }
        """
        results = []
        cursor = None

        while True:
            params = {"accountIds": account_id, "state": "active"}
            if cursor:
                params["cursor"] = cursor

            url = f"{self.base_url}/web/api/v2.1/sites"
            resp = requests.get(url, headers=self.headers, params=params, timeout=30)

            if resp.status_code != 200:
                print(f"[ERRO] /sites → {resp.status_code}: {resp.text[:300]}")
                break

            body = resp.json()
            results.extend(body.get("data", {}).get("sites", []))
            cursor = body.get("pagination", {}).get("nextCursor")
            if not cursor:
                break

        return results

    # =========================================================================
    # COLETA DE DADOS
    # =========================================================================

    def get_accounts(self):
        print("[INFO] Coletando Accounts...")
        return self._get_paginated("accounts")

    def get_sites(self, account_id):
        return self._get_sites_paginated(account_id)

    def get_agents(self, site_id):
        """
        Retorna todos os agentes ativos de um Site.
        Nota: /agents não suporta o param 'fields' — retorna o objeto completo.
        """
        return self._get_paginated(
            "agents",
            params={
                "siteIds": site_id,
                "isDecommissioned": "false",
            },
        )

    # =========================================================================
    # PARSING DE CAMPOS DO SITE
    # =========================================================================

    def parse_site_info(self, site):
        """
        Extrai os campos relevantes de um objeto site.

        Campos confirmados na doc v2.1:
          - activeLicenses       → integer
          - sku                  → enum (deprecated mas ainda retornado)
          - licenses.bundles     → features principais (Complete, Control, etc.)
          - licenses.modules     → add-ons (Vigilance, Cloud Funnel, etc.)
        """
        licenses = site.get("licenses") or {}

        bundles = licenses.get("bundles") or []
        features = ", ".join(
            b.get("displayName") or b.get("name") or ""
            for b in bundles
            if b.get("displayName") or b.get("name")
        ) or None

        modules_list = licenses.get("modules") or []
        modules = ", ".join(
            m.get("displayName") or m.get("name") or ""
            for m in modules_list
            if m.get("displayName") or m.get("name")
        ) or None

        return {
            "site_id":         site.get("id"),
            "site_name":       site.get("name", "N/A"),
            "sku":             site.get("sku", "N/A"),
            "active_licenses": site.get("activeLicenses", 0),
            "features":        features,
            "modules":         modules,
        }

    # =========================================================================
    # AGREGAÇÃO LOCAL DE AGENTES
    # =========================================================================

    def count_agents(self, agents):
        """
        Agrega agentes por machineType localmente.
        Valores do campo machineType (doc v2.1):
          desktop, laptop → Workstations
          server          → Servers
        """
        workstation_types = {"desktop", "laptop"}
        server_types      = {"server"}
        counts = {"workstations": 0, "servers": 0, "other": 0}

        for agent in agents:
            mt = (agent.get("machinetype") or "").lower()
            if mt in workstation_types:
                counts["workstations"] += 1
            elif mt in server_types:
                counts["servers"] += 1
            else:
                counts["other"] += 1

        return counts

    # =========================================================================
    # PRINT REALTIME
    # =========================================================================

    def print_site(self, acc_name, site_info, counts):
        print(f"\n[ACCOUNT] {acc_name}", flush=True)
        print(f"  └── [SITE] {site_info['site_name']}", flush=True)
        print(f"      ├── SKU: {site_info['sku']}", flush=True)
        print(f"      ├── Active Licenses: {site_info['active_licenses']}", flush=True)
        print(f"      ├── Workstations: {counts['workstations']}", flush=True)
        print(f"      ├── Servers: {counts['servers']}", flush=True)
        print(f"      ├── Features: {site_info['features'] or 'None'}", flush=True)
        print(f"      └── Modules: {site_info['modules'] or 'None'}", flush=True)

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _sku_to_license_type(self, sku):
        if not sku:
            return "unknown"
        sku_lower = sku.lower()
        if "complete" in sku_lower:
            return "complete"
        if "control" in sku_lower:
            return "control"
        if "core" in sku_lower:
            return "core"
        return sku_lower

    # =========================================================================
    # RUNNER
    # =========================================================================

    def run(self):
        accounts = self.get_accounts()

        if not accounts:
            print("[AVISO] Nenhuma Account encontrada. Verifique as permissões do token.")
            return

        report_rows = []

        for acc in accounts:
            acc_id   = acc.get("id")
            acc_name = acc.get("name", "N/A")

            sites = self.get_sites(acc_id)
            if not sites:
                print(f"[AVISO] Nenhum site ativo em: {acc_name}")
                continue

            for site in sites:
                site_info    = self.parse_site_info(site)
                site_id      = site_info["site_id"]
                license_type = self._sku_to_license_type(site_info["sku"])

                agents = self.get_agents(site_id)
                counts = self.count_agents(agents)

                self.print_site(acc_name, site_info, counts)

                row = {
                    "Account":               acc_name,
                    "Site":                  site_info["site_name"],
                    "SKU":                   site_info["sku"],
                    "License_Type":          license_type,
                    "Active_Licenses":       site_info["active_licenses"],
                    "Features":              site_info["features"] or "",
                    "Modules":               site_info["modules"] or "",
                    "Complete_Workstations": counts["workstations"] if license_type == "complete" else 0,
                    "Complete_Servers":      counts["servers"]      if license_type == "complete" else 0,
                    "Control_Workstations":  counts["workstations"] if license_type == "control"  else 0,
                    "Control_Servers":       counts["servers"]      if license_type == "control"  else 0,
                    "Other_Endpoints":       counts["other"],
                    "Total_Agents":          len(agents),
                }
                report_rows.append(row)

        output_file = "mssp_consumption_pro.csv"
        if report_rows:
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=report_rows[0].keys())
                writer.writeheader()
                writer.writerows(report_rows)
            print(f"\n[SUCESSO] {output_file} gerado com {len(report_rows)} linha(s).")
        else:
            print("[AVISO] Nenhum dado coletado.")


if __name__ == "__main__":
    try:
        app = S1MSSPPro()
        app.run()
    except ValueError as e:
        print(f"[ERRO DE CONFIGURAÇÃO] {e}")
    except Exception as e:
        print(f"[ERRO CRÍTICO] {e}")
        raise
