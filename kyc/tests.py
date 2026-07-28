import os

from django.test import TestCase, override_settings
from kyc.models import KycDocumentType
from kyc.document_extraction import detect_document_type, learn_document_keywords

class KycDocumentTypeAutoLearningTest(TestCase):
    def setUp(self):
        KycDocumentType.objects.all().delete()
        
        self.cni = KycDocumentType.objects.create(
            code="piece_identite",
            label="Pièce d'identité",
            keywords="CARTE NATIONALE, CARTE D'IDENTITE, CNI",
            min_score=2.0
        )
        self.passport = KycDocumentType.objects.create(
            code="passeport",
            label="Passeport",
            keywords="PASSEPORT, PASSPORT, N° PASSEPORT",
            min_score=2.0
        )
        self.water_bill = KycDocumentType.objects.create(
            code="facture_eau",
            label="Facture d'eau",
            keywords="SDE, FACTURE, EAU, ABONNEMENT",
            min_score=2.0
        )

    def test_document_classification_by_keywords(self):
        text_cni = "RÉPUBLIQUE DU SÉNÉGAL CARTE NATIONALE D'IDENTITÉ CNI CEDEAO"
        doc_type = detect_document_type(text_cni, "my_cni.jpg")
        self.assertEqual(doc_type, "piece_identite")

        text_water = "FACTURE DE CONSOMMATION EAU APPAREIL SDE ABONNEMENT"
        doc_type = detect_document_type(text_water, "invoice.pdf")
        self.assertEqual(doc_type, "facture_eau")

        text_unknown = "BONJOUR LE MONDE CECI EST UN DOCUMENT NON APPARENTÉ"
        doc_type = detect_document_type(text_unknown, "unknown.pdf")
        self.assertEqual(doc_type, "")

    def test_document_classification_by_keywords_country_specific(self):
                                                                         
        sn_water_bill = KycDocumentType.objects.create(
            code="facture_eau",
            label="Facture d'eau du Sénégal",
            keywords="SDE, FACTURE, SENEGAL",
            min_score=2.0,
            filiale="BOA SN"
        )
                                                                              
        ci_water_bill = KycDocumentType.objects.create(
            code="facture_eau",
            label="Facture d'eau de Côte d'Ivoire",
            keywords="SODECI, FACTURE, IVOIRE",
            min_score=2.0,
            filiale="BOA CI"
        )

                                             
        text_sn = "FACTURE SDE SENEGAL POUR LE CLIENT"
        doc_type = detect_document_type(text_sn, "invoice.pdf", filiale="BOA SN")
        self.assertEqual(doc_type, "facture_eau")

                                                                                                    
        resolved_dt_sn = KycDocumentType.objects.filter(code=doc_type, filiale="BOA SN").first()
        self.assertEqual(resolved_dt_sn.label, "Facture d'eau du Sénégal")

                                             
        text_ci = "FACTURE SODECI DE COTE D'IVOIRE"
        doc_type_ci = detect_document_type(text_ci, "invoice.pdf", filiale="BOA CI")
        self.assertEqual(doc_type_ci, "facture_eau")

        resolved_dt_ci = KycDocumentType.objects.filter(code=doc_type_ci, filiale="BOA CI").first()
        self.assertEqual(resolved_dt_ci.label, "Facture d'eau de Côte d'Ivoire")

    def test_auto_learning_mechanism(self):
        doc_text = (
            "FACTURE SDE EAU ELEC ABONNEMENT SDE SENECLEC FACTURE COMPTEUR SDE SDE SDE "
            "FACTURE DE CONSOMMATION EAU PROPRIETAIRE"
        )
        learn_document_keywords(doc_text, "facture_eau")
        
        self.water_bill.refresh_from_db()
        keywords_list = self.water_bill.get_keyword_list()
        
        self.assertIn("SDE", keywords_list)
        self.assertIn("FACTURE", keywords_list)
        self.assertTrue(len(keywords_list) > 4)

    def test_auto_learning_mechanism_country_specific(self):
        sn_water_bill = KycDocumentType.objects.create(
            code="facture_eau",
            label="Facture d'eau du Sénégal",
            keywords="SDE, FACTURE, SENEGAL",
            min_score=2.0,
            filiale="BOA SN"
        )
        doc_text = "FACTURE DE SENELEC SENEGAL ELECTRICITE COMPTEUR SENELEC SENELEC"
        learn_document_keywords(doc_text, "facture_eau", filiale="BOA SN")
        
        sn_water_bill.refresh_from_db()
        keywords_list = sn_water_bill.get_keyword_list()
        self.assertIn("SENELEC", keywords_list)
        
                                              
        self.water_bill.refresh_from_db()
        global_keywords_list = self.water_bill.get_keyword_list()
        self.assertNotIn("SENELEC", global_keywords_list)


from kyc.models import KycDocumentExtraction, Kyc_pm
from kyc.views import _build_kyc_pm_document_matches

class KycPmMatchingTest(TestCase):
    def setUp(self):
                                   
        self.pm_client = Kyc_pm.objects.create(
            CLIENT="BOA H HOLDING",
            RCSNO="RCS-DK-2026-B-1234",
            NUMERO_FISCAL="NIF-9988776655",
            ADRESSE_SOCIALE="Dakar, Senegal",
            INTITULE_COMPTE="BOA H HOLDING CO",
            FILIALE="BOA SN",
            AGENCE="001",
        )
        
    def test_pm_matching_by_rcs(self):
                                                              
        doc = KycDocumentExtraction.objects.create(
            document_type="registre_commerce",
            original_filename="rc.pdf",
            client_type="pm",
            numero_document="RCS-DK-2026-B-1234",
            nom="BOA H HOLDING",
            adresse="Dakar, Senegal",
        )
        
        matches, summary = _build_kyc_pm_document_matches(KycDocumentExtraction.objects.filter(pk=doc.pk))
        
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["client"].pk, self.pm_client.pk)
        self.assertEqual(matches[0]["match_rate"], 100)
        self.assertEqual(summary["documents_matched"], 1)
        self.assertEqual(summary["clients_matched"], 1)
        
    def test_pm_matching_by_nif(self):
                                                              
        doc = KycDocumentExtraction.objects.create(
            document_type="nif_cert",
            original_filename="nif.pdf",
            client_type="pm",
            numero_identification_nationale="NIF-9988776655",
            nom="BOA H HOLDING",
        )
        
        matches, summary = _build_kyc_pm_document_matches(KycDocumentExtraction.objects.filter(pk=doc.pk))
        
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["client"].pk, self.pm_client.pk)
        self.assertEqual(matches[0]["match_rate"], 100)


from kyc.models import KycFieldVisibilityConfig, Kyc_pp
from kyc.views import _build_kyc_pp_document_matches, _build_kyc_pp_match_action_items, _get_field_sources, _field_visibility_configs_cache

class KycDocumentFieldSourcesTest(TestCase):
    def setUp(self):
        KycFieldVisibilityConfig.objects.all().delete()
        global _field_visibility_configs_cache
        _field_visibility_configs_cache = None

        self.client_pp = Kyc_pp.objects.create(
            CLIENT="SYLLA MAMADOU",
            NUMID="123456789",
            DATNAIS="1990-01-01",
            PAYNAIS="SENEGAL",
            FILIALE="BOA SN",
            ADRESSE="",                                                                        
        )

    def test_field_source_filtering_in_matching(self):
        KycFieldVisibilityConfig.objects.create(
            client_type="pp",
            filiales=["BOA SN"],
            field_sources={"DATNAIS": "passeport"}
        )
        global _field_visibility_configs_cache
        _field_visibility_configs_cache = None

        doc = KycDocumentExtraction.objects.create(
            document_type="piece_identite",
            original_filename="cni.pdf",
            client_type="pp",
            numero_document="123456789",
            date_naissance="1991-01-01",                                                                      
            adresse="Dakar, Senegal",                                          
        )

        matches, summary = _build_kyc_pp_document_matches(KycDocumentExtraction.objects.filter(pk=doc.pk))
        self.assertEqual(len(matches), 1)
        match = matches[0]
        for sug in match["suggestions"]:
            self.assertNotEqual(sug["field"], "DATNAIS")

        actions = _build_kyc_pp_match_action_items(match)
                                                   
        self.assertTrue(any(act["field"] == "ADRESSE" for act in actions))
                                                     
        self.assertFalse(any(act["field"] == "DATNAIS" for act in actions))

    def test_field_source_matching_when_type_matches(self):
        KycFieldVisibilityConfig.objects.create(
            client_type="pp",
            filiales=["BOA SN"],
            field_sources={"DATNAIS": "passeport"}
        )
        global _field_visibility_configs_cache
        _field_visibility_configs_cache = None

        doc = KycDocumentExtraction.objects.create(
            document_type="passeport",
            original_filename="passport.pdf",
            client_type="pp",
            numero_document="123456789",
            date_naissance="1991-01-01",
            adresse="Dakar, Senegal",                                          
        )

        matches, summary = _build_kyc_pp_document_matches(KycDocumentExtraction.objects.filter(pk=doc.pk))
        self.assertEqual(len(matches), 1)
        match = matches[0]
        actions = _build_kyc_pp_match_action_items(match)
                                                                                 
        has_datnais = any(act["field"] == "DATNAIS" for act in actions)
        self.assertTrue(has_datnais)

    def test_propagate_field_sources_to_all_filiales(self):
        from django.urls import reverse
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(username="testgroupuser", password="password", filiale="BOA Group")
        self.client.login(username="testgroupuser", password="password")

                                                                        
        KycFieldVisibilityConfig.objects.create(client_type="pp", filiales=["BOA SN"], field_sources={"ADRESSE": "facture_eau"})
        KycFieldVisibilityConfig.objects.create(client_type="pp", filiales=["BOA CI"], field_sources={"ADRESSE": "facture_electricite"})

                                                                   
        post_data = {
            "action": "save_document_field_sources",
            "apply_to_all_filiales": "1",
            "source_pp_DATNAIS": "passeport",
            "source_pp_ADRESSE": "piece_identite",
        }
        
        response = self.client.post(reverse("kyc:document_extraction"), post_data)
        self.assertEqual(response.status_code, 302)                   

                                                                                                                                         
        configs = KycFieldVisibilityConfig.objects.filter(client_type="pp")
        self.assertTrue(configs.count() >= 3)
        for config in configs:
            self.assertEqual(config.field_sources.get("DATNAIS"), "passeport")
            self.assertEqual(config.field_sources.get("ADRESSE"), "piece_identite")

    def test_dynamic_field_source_filtering_by_visibility_config(self):
        from django.urls import reverse
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(username="testgroupuser2", password="password", filiale="BOA Group")
        self.client.login(username="testgroupuser2", password="password")

                                                                                                                           
        KycFieldVisibilityConfig.objects.create(
            client_type="pp",
            filiales=["BOA SN"],
            display_fields=[],
            empty_check_fields=["CLIENT", "NUMID"]
        )

        response = self.client.get(reverse("kyc:document_extraction") + "?filiale=BOA SN")
        self.assertEqual(response.status_code, 200)

                                                           
        sections = response.context["document_field_source_sections"]
        pp_section = next(sec for sec in sections if sec["client_type"] == "pp")
        
                                                              
        fields_names = [f[0] for f in pp_section["fields"]]
        self.assertIn("CLIENT", fields_names)
        self.assertIn("NUMID", fields_names)
        self.assertNotIn("DATNAIS", fields_names)
        self.assertNotIn("ADRESSE", fields_names)


from kyc.forms import DataQualityRuleForm

class DataQualityRuleFormTest(TestCase):
    def test_default_filiale_choices(self):
        form = DataQualityRuleForm()
        from kyc.models import Filiales
        expected_choices = [(f[0], f[0]) for f in Filiales]
        self.assertEqual(list(form.fields['filiale'].choices), expected_choices)

    def test_restricted_filiale_choices(self):
        form = DataQualityRuleForm(filiale_choices=["BOA CI"])
        self.assertEqual(list(form.fields['filiale'].choices), [("BOA CI", "BOA CI")])


from django.urls import reverse
from django.contrib.auth import get_user_model
from kyc.models import DataQualityRule

class DataQualityRuleViewsTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="testadmin", password="password", organe="PASS")
        self.client.login(username="testadmin", password="password")
        self.rule = DataQualityRule.objects.create(
            name="Test Rule",
            applicability="PP",
            field_name="CLIENT",
            control_type="simple",
            parameter="existence",
            filiale="|BOA SN|BOA CI|"
        )

    def test_quality_control_view_includes_filiales_display(self):
        response = self.client.get(reverse('kyc:quality_control'))
        self.assertEqual(response.status_code, 200)
        rules = response.context['rules']
        self.assertTrue(len(rules) > 0)
        rule_item = next(item for item in rules if item['rule'].id == self.rule.id)
        self.assertEqual(rule_item['filiales_display'], "BOA SN, BOA CI")

    def test_non_anom_view_for_group_user(self):
        response = self.client.get(reverse('non_anom'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('rules', response.context)
        rules = response.context['rules']
        self.assertTrue(any(item['rule'].id == self.rule.id for item in rules))
        
        rule_item = next(item for item in rules if item['rule'].id == self.rule.id)
        self.assertEqual(rule_item['filiales_summary']['display'], "BOA SN, BOA CI")
        self.assertEqual(rule_item['filiales_summary']['visible'], ["BOA SN", "BOA CI"])
        self.assertEqual(rule_item['filiales_summary']['hidden_count'], 0)

    def test_non_anom_view_for_filiale_user(self):
        User = get_user_model()
        sn_user = User.objects.create_user(username="testsn", password="password", organe="Conformité", filiale="BOA SN")
        self.client.login(username="testsn", password="password")
        response = self.client.get(reverse('non_anom'))
        self.assertEqual(response.status_code, 200)
        rules = response.context['rules']
        self.assertTrue(any(item['rule'].id == self.rule.id for item in rules))
        
                                                                             
        rule_item = next(item for item in rules if item['rule'].id == self.rule.id)
        self.assertEqual(rule_item['filiales_summary']['display'], "BOA SN")
        self.assertEqual(rule_item['filiales_summary']['visible'], ["BOA SN"])
        self.assertEqual(rule_item['filiales_summary']['hidden_count'], 0)

        ne_user = User.objects.create_user(username="testne", password="password", organe="Conformité", filiale="BOA NE")
        self.client.login(username="testne", password="password")
        response = self.client.get(reverse('non_anom'))
        self.assertEqual(response.status_code, 200)
        rules = response.context['rules']
        self.assertFalse(any(item['rule'].id == self.rule.id for item in rules))

    def test_non_anom_view_detail_modal(self):
        response = self.client.get(reverse('non_anom') + f"?rule={self.rule.id}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['show_rule_modal'])
        self.assertEqual(response.context['selected_rule'].id, self.rule.id)

    def test_export_rule_failures_filename(self):
        response = self.client.get(reverse('kyc:export_rule_failures', kwargs={'rule_id': self.rule.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertEqual(response['Content-Disposition'], 'attachment; filename="test_rule.xlsx"')

    def test_ppe_view_risk_distribution_and_export(self):
        from kyc.models import Kyc_pp
        Kyc_pp.objects.create(
            CLIENT="Client A", PPE="O", RISQUE="Risque Eleve",
            NUMID="123", DATNAIS="1990-01-01", ADRESSE="Adresse A", TEL="771234567"
        )
        Kyc_pp.objects.create(
            CLIENT="Client B", PPE="O", RISQUE="Risque Moyen",
            NUMID="", DATNAIS="1995-01-01", ADRESSE="Adresse B", TEL="771234568"
        )

        response = self.client.get(reverse('ppe'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('kpi_cards', response.context)
        
        kpi_cards = response.context['kpi_cards']
        risk_card = kpi_cards[0]
        self.assertEqual(risk_card['label'], 'Répartition par Risque')
        self.assertTrue(risk_card['show_modal'])
        
        export_response = self.client.get(reverse('export_ppe') + "?incompletes=1")
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response['Content-Type'], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn('PPE_incomplets', export_response['Content-Disposition'])

    def test_devise_pp_dynamic_incomplete_filtering(self):
        from kyc.models import Kyc_pp, KycFieldVisibilityConfig
        Kyc_pp.objects.all().delete()
        KycFieldVisibilityConfig.objects.all().delete()
        
        KycFieldVisibilityConfig.objects.create(
            client_type="pp",
            filiales=["BOA SN"],
            empty_check_fields=["NUMID"]
        )
        
        Kyc_pp.objects.create(
            CLIENT="Client SN 1", FILIALE="BOA SN", DEVISE="EUR",
            NUMID="SN123", ADRESSE="", TEL=""
        )
        Kyc_pp.objects.create(
            CLIENT="Client SN 2", FILIALE="BOA SN", DEVISE="EUR",
            NUMID="", ADRESSE="Adresse", TEL="123"
        )
        
        response = self.client.get(reverse('devise'))
        self.assertEqual(response.status_code, 200)
        
        kpi_cards = response.context['kpi_cards']
        incomplete_card = next(c for c in kpi_cards if c['label'] == 'Comptes Incomplets')
        self.assertEqual(incomplete_card['value'], 1)
        
        export_response = self.client.get(reverse('export_devise_pp') + "?incompletes=1")
        self.assertEqual(export_response.status_code, 200)
        self.assertIn('Comptes_en_devise_PP_incomplets', export_response['Content-Disposition'])

    def test_non_resid_pm_dynamic_incomplete_filtering(self):
        from kyc.models import Kyc_pm, KycFieldVisibilityConfig
        Kyc_pm.objects.all().delete()
        KycFieldVisibilityConfig.objects.all().delete()
        
        KycFieldVisibilityConfig.objects.create(
            client_type="pm",
            filiales=["BOA SN"],
            empty_check_fields=["RCSNO"]
        )
        
        Kyc_pm.objects.create(
            CLIENT="Client SN PM 1", FILIALE="BOA SN", RESID="N",
            RCSNO="RC-SN-123", NUMERO_FISCAL="", ADRESSE_SOCIALE=""
        )
        Kyc_pm.objects.create(
            CLIENT="Client SN PM 2", FILIALE="BOA SN", RESID="N",
            RCSNO="", NUMERO_FISCAL="FISCAL-123", ADRESSE_SOCIALE="Adresse"
        )
        
        response = self.client.get(reverse('non_resid_pm'))
        self.assertEqual(response.status_code, 200)
        
        kpi_cards = response.context['kpi_cards']
        incomplete_card = next(c for c in kpi_cards if c['label'] == 'PM Incomplets')
        self.assertEqual(incomplete_card['value'], 1)
        
        export_response = self.client.get(reverse('export_non_resid_pm') + "?incompletes=1")
        self.assertEqual(export_response.status_code, 200)
        self.assertIn('Comptes_non_resid_PM_incomplets', export_response['Content-Disposition'])




class ProtectedMediaAccessTest(TestCase):
    """E-2 : les documents KYC televerses ne doivent jamais etre servis sans controle."""

    def setUp(self):
        import tempfile
        from django.contrib.auth import get_user_model
        from kyc.models import KycDocumentExtraction

        User = get_user_model()
        self.media_dir = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_dir)
        self.override.enable()
        self.addCleanup(self.override.disable)

        os.makedirs(os.path.join(self.media_dir, "images"))
        os.makedirs(os.path.join(self.media_dir, "document_extraction"))
        with open(os.path.join(self.media_dir, "images", "logo.png"), "wb") as f:
            f.write(b"PNG-LOGO")
        with open(os.path.join(self.media_dir, "document_extraction", "cni.pdf"), "wb") as f:
            f.write(b"%PDF-SECRET")
                                                                      
        self.outside = os.path.join(os.path.dirname(self.media_dir), "secret_outside.txt")
        with open(self.outside, "w") as f:
            f.write("SECRET")
        self.addCleanup(lambda: os.path.exists(self.outside) and os.remove(self.outside))

        self.uploader = User.objects.create_user(
            username="uploader@boa.local", password="MotDePasseTest2026!",
            organe="Chargé Client", filiale="BOA SN")
        self.same_filiale = User.objects.create_user(
            username="collegue@boa.local", password="MotDePasseTest2026!",
            organe="Chargé Client", filiale="BOA SN")
        self.other_filiale = User.objects.create_user(
            username="etranger@boa.local", password="MotDePasseTest2026!",
            organe="Chargé Client", filiale="BOA CI")

        KycDocumentExtraction.objects.create(
            document_type="piece_identite",
            uploaded_file="document_extraction/cni.pdf",
            original_filename="cni.pdf",
            uploaded_by=self.uploader,
        )

    def test_branding_reste_public(self):
        """Le logo doit rester accessible : il s'affiche sur les pages sans session."""
        response = self.client.get("/media/images/logo.png")
        self.assertEqual(response.status_code, 200)

    def test_document_kyc_refuse_a_anonyme(self):
        response = self.client.get("/media/document_extraction/cni.pdf")
        self.assertIn(response.status_code, (301, 302))
        self.assertIn("login", response["Location"])

    def test_document_kyc_refuse_hors_filiale(self):
        self.client.force_login(self.other_filiale)
        response = self.client.get("/media/document_extraction/cni.pdf")
        self.assertEqual(response.status_code, 403)

    def test_document_kyc_autorise_pour_le_deposant(self):
        self.client.force_login(self.uploader)
        response = self.client.get("/media/document_extraction/cni.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_document_kyc_autorise_meme_filiale(self):
        self.client.force_login(self.same_filiale)
        response = self.client.get("/media/document_extraction/cni.pdf")
        self.assertEqual(response.status_code, 200)

    def test_traversee_de_repertoire_bloquee(self):
        self.client.force_login(self.uploader)
        response = self.client.get("/media/document_extraction/../../secret_outside.txt")
        self.assertNotEqual(response.status_code, 200)

    def test_fichier_orphelin_refuse(self):
        """Un fichier sans enregistrement en base n'est servi a personne."""
        with open(os.path.join(self.media_dir, "document_extraction", "orphelin.pdf"), "wb") as f:
            f.write(b"%PDF")
        self.client.force_login(self.uploader)
        response = self.client.get("/media/document_extraction/orphelin.pdf")
        self.assertEqual(response.status_code, 403)


class PasswordValidationOnResetTest(TestCase):
    """M-2 : ResetPasswordForm doit appliquer les AUTH_PASSWORD_VALIDATORS."""

    def test_mot_de_passe_trivial_refuse(self):
        from kyc.forms import ResetPasswordForm
        form = ResetPasswordForm(data={"new_password": "1234", "confirm_password": "1234"})
        self.assertFalse(form.is_valid())

    def test_mot_de_passe_tout_numerique_refuse(self):
        from kyc.forms import ResetPasswordForm
        form = ResetPasswordForm(data={"new_password": "9081726354", "confirm_password": "9081726354"})
        self.assertFalse(form.is_valid())

    def test_mot_de_passe_robuste_accepte(self):
        from kyc.forms import ResetPasswordForm
        form = ResetPasswordForm(data={"new_password": "Tr#sB0nMdp2026", "confirm_password": "Tr#sB0nMdp2026"})
        self.assertTrue(form.is_valid(), form.errors)


class UploadedDocumentTypeValidationTest(TestCase):
    """M-3 : validation extension + signature binaire des fichiers televerses."""

    def _fichier(self, nom, contenu):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return SimpleUploadedFile(nom, contenu)

    def test_pdf_valide_accepte(self):
        from kyc.views import _validate_uploaded_document
        self.assertIsNone(_validate_uploaded_document(self._fichier("cni.pdf", b"%PDF-1.4 ...")))

    def test_extension_interdite_refusee(self):
        from kyc.views import _validate_uploaded_document
        self.assertIsNotNone(_validate_uploaded_document(self._fichier("payload.html", b"<script>alert(1)</script>")))

    def test_html_renomme_en_pdf_refuse(self):
        """Un fichier HTML renomme .pdf est bloque par la signature binaire."""
        from kyc.views import _validate_uploaded_document
        self.assertIsNotNone(_validate_uploaded_document(self._fichier("faux.pdf", b"<html><body>x</body></html>")))

    def test_png_valide_accepte(self):
        from kyc.views import _validate_uploaded_document
        self.assertIsNone(_validate_uploaded_document(self._fichier("photo.png", b"\x89PNG\r\n\x1a\n rest")))
