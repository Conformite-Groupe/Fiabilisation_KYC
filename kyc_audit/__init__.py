# -*- coding: utf-8 -*-
"""Audit de la qualité et de la complétude des données KYC (BOA).

Enchaînement : dataset -> completude / qualite / scoring -> pipeline -> deck.
Point d'entrée : generate_report.py à la racine du projet.
"""
__all__ = ["config", "dataset", "completude", "qualite", "scoring", "pipeline",
           "theme", "deck"]
