import os

views_path = r"c:\Users\mamsylla\OneDrive - BANK OF AFRICA(1)\Documents\Projets\2025\Plateforme notatio kyc v2\Fiabilisation_kyc - Copie\kyc\views.py"

with open(views_path, 'r', encoding='utf-8') as f:
    content = f.read()

good_part = r"""    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        data_dir = (request.POST.get("data_dir") or "").strip()
        filiales = (request.POST.get("filiales") or "").strip()
        only = (request.POST.get("only") or "").strip()
        bulk_size = (request.POST.get("bulk_size") or "").strip()
        taux_clear = request.POST.get("taux_clear") == "on"

        script = None
        if action == "run_kyc":
            script = "import_kyc.py"
        elif action == "run_premier":
            script = "import_premier.py"

        if not script:
            messages.error(request, "Action d'import inconnue.")
        else:
            env = os.environ.copy()
            if data_dir:
                env["KYC_DATA_DIR"] = data_dir
            if filiales:
                env["KYC_FILIALES"] = filiales
            if bulk_size:
                env["KYC_BULK_SIZE"] = bulk_size
            if only:
                env["KYC_ONLY"] = only
            if taux_clear:
                env["KYC_TAUX_CLEAR"] = "1"
            elif "KYC_TAUX_CLEAR" in env:
                env.pop("KYC_TAUX_CLEAR", None)

            cmd = [sys.executable, str(settings.BASE_DIR / script)]
            start_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            detail_path = os.path.join(run_dir, f"{action}_{run_id}.log")
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(settings.BASE_DIR),
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                status = "SUCCESS" if result.returncode == 0 else "FAILED"
                with open(detail_path, "w", encoding="utf-8") as df:
                    df.write(f"CMD: {cmd}\n")
                    df.write(f"START: {start_ts}\n")
                    df.write(f"RETURN: {result.returncode}\n")
                    df.write(f"DATA_DIR: {data_dir}\n")
                    df.write(f"FILIALES: {filiales}\n")
                    df.write(f"ONLY: {only}\n")
                    df.write(f"BULK_SIZE: {bulk_size}\n")
                    df.write(f"TAUX_CLEAR: {taux_clear}\n")
                    df.write("\n--- STDOUT ---\n")
                    df.write(result.stdout or "")
                    df.write("\n--- STDERR ---\n")
                    df.write(result.stderr or "")

                with open(history_path, "a", encoding="utf-8") as hf:
                    hf.write(f"{start_ts} | {action} | {status} | log={detail_path}\n")

                if status == "SUCCESS":
                    # Invalider le cache des règles de qualité après un import réussi
                    current_v = cache.get('quality_control_rules_version', 1)
                    cache.set('quality_control_rules_version', current_v + 1, timeout=None)
                    messages.success(request, "Import terminé avec succès.")
                else:
                    messages.error(request, f"Import échoué (code {result.returncode}).")

            except Exception as e:
                messages.error(request, f"Erreur d'ex\u00e9cution: {e}")"""

content_norm = content.replace('\r\n', '\n')
good_part_norm = good_part.replace('\r\n', '\n')

post_token = '    if request.method == "POST":'
except_token = '            except Exception as e:\n                messages.error(request, f"Erreur d\'ex\u00e9cution: {e}")'

idx_post = content_norm.find(post_token)
if idx_post != -1:
                                                              
                                                                                         
    idx_except = content_norm.find('            except Exception as e:', idx_post)
    if idx_except != -1:
                                                                  
        idx_msg = content_norm.find('messages.error(request, f"Erreur', idx_except)
        if idx_msg != -1 and idx_msg < idx_except + 150:
                              
            idx_eol = content_norm.find('\n', idx_msg)
            if idx_eol != -1:
                end_idx = idx_eol + 1
                new_content = content_norm[:idx_post] + good_part_norm + content_norm[end_idx:]
                with open(views_path, 'w', encoding='utf-8', newline='\r\n') as f:
                    f.write(new_content)
                print("PATCH APPLIED VIA SCANNING")
            else:
                print("EOL NOT FOUND")
        else:
            print("MSG NOT FOUND")
    else:
        print("EXCEPT TOKEN NOT FOUND")
else:
    print("POST TOKEN NOT FOUND")
