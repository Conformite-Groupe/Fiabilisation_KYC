## Appreciation Qualite

      Appreciation_qualite[Taux_qualite_agent<=80 & Notation=="Très bien"]="Insatisfaisant"
        Appreciation_qualite[Taux_qualite_agent<=80 & Notation=="Bien"]="Insatisfaisant"
        Appreciation_qualite[Taux_qualite_agent<=80 & Notation=="Passable"]="Insatisfaisant"
        Appreciation_qualite[Taux_qualite_agent<=80 & Notation=="Insuffisant"]="Insatisfaisant"


        Appreciation_qualite[(Taux_qualite_agent<100 & Taux_qualite_agent>80) & Notation=="Très bien"]="Satisfaisant"
        Appreciation_qualite[(Taux_qualite_agent<100 & Taux_qualite_agent>80) & Notation=="Bien"]="Satisfaisant"
        Appreciation_qualite[(Taux_qualite_agent<100 & Taux_qualite_agent>80) & Notation=="Passable"]="Insatisfaisant"
        Appreciation_qualite[(Taux_qualite_agent<100 & Taux_qualite_agent>80) & Notation=="Insuffisant"]="Insatisfaisant"

        Appreciation_qualite[Taux_qualite_agent==100 & Notation=="Très bien"]="Très satisfaisant"
        Appreciation_qualite[Taux_qualite_agent==100 & Notation=="Bien"]="Satisfaisant"
        Appreciation_qualite[Taux_qualite_agent==100 & Notation=="Passable"]="Satisfaisant"
        Appreciation_qualite[Taux_qualite_agent==100 & Notation=="Insuffisant"]="Insatisfaisant"


        Appreciation_qualite[Taux_qualite_agent<=80 & (is.na(Notation)=="TRUE" | Notation=="")]="Insatisfaisant"

        Appreciation_qualite[(Taux_qualite_agent < 100 & Taux_qualite_agent > 80) & (is.na(Notation)=="TRUE" | Notation=="") ]="Satisfaisant"

        Appreciation_qualite[Taux_qualite_agent==100 & (is.na(Notation)=="TRUE" | Notation=="")]="Très satisfaisant"

 ## Appreciation Globale

         if (trimestre_actuel=="1") {

          Appreciation_Globale=""

          Appreciation_Globale[TauxEvolution<=5 & Appreciation_qualite=="Très satisfaisant"]="Faible++"
          Appreciation_Globale[TauxEvolution<=5 & Appreciation_qualite=="Satisfaisant"]="Faible+"
          Appreciation_Globale[TauxEvolution<=5 & Appreciation_qualite=="Insatisfaisant"]="Faible-"

          Appreciation_Globale[(TauxEvolution>5 & TauxEvolution <=30) & Appreciation_qualite=="Très satisfaisant"]="Moyen++"
          Appreciation_Globale[(TauxEvolution>5 & TauxEvolution <=30) & Appreciation_qualite=="Satisfaisant"]="Moyen+"
          Appreciation_Globale[(TauxEvolution>5 & TauxEvolution <=30) & Appreciation_qualite=="Insatisfaisant"]="Moyen-"

          Appreciation_Globale[TauxEvolution>30 & Appreciation_qualite=="Très satisfaisant"]="Bon++"
          Appreciation_Globale[TauxEvolution>30 & Appreciation_qualite=="Satisfaisant"]="Bon+"
           Appreciation_Globale[TauxEvolution>30 & Appreciation_qualite=="Insatisfaisant"]="Bon-"
         }

           if (trimestre_actuel=="2") {

          Appreciation_Globale=""

          Appreciation_Globale[TauxEvolution<=30 & Appreciation_qualite=="Très satisfaisant"]="Faible++"
          Appreciation_Globale[TauxEvolution<=30 & Appreciation_qualite=="Satisfaisant"]="Faible+"
          Appreciation_Globale[TauxEvolution<=30 & Appreciation_qualite=="Insatisfaisant"]="Faible-"

          Appreciation_Globale[(TauxEvolution>30 & TauxEvolution <=60) & Appreciation_qualite=="Très satisfaisant"]="Moyen++"
          Appreciation_Globale[(TauxEvolution>30 & TauxEvolution <=60) & Appreciation_qualite=="Satisfaisant"]="Moyen+"
          Appreciation_Globale[(TauxEvolution>30 & TauxEvolution <=60) & Appreciation_qualite=="Insatisfaisant"]="Moyen-"

          Appreciation_Globale[TauxEvolution>60 & Appreciation_qualite=="Très satisfaisant"]="Bon++"
          Appreciation_Globale[TauxEvolution>60 & Appreciation_qualite=="Satisfaisant"]="Bon+"
           Appreciation_Globale[TauxEvolution>60 & Appreciation_qualite=="Insatisfaisant"]="Bon-"
         }

           if (trimestre_actuel=="3") {

          Appreciation_Globale=""

          Appreciation_Globale[TauxEvolution<=60 & Appreciation_qualite=="Très satisfaisant"]="Faible++"
          Appreciation_Globale[TauxEvolution<=60 & Appreciation_qualite=="Satisfaisant"]="Faible+"
          Appreciation_Globale[TauxEvolution<=60 & Appreciation_qualite=="Insatisfaisant"]="Faible-"

          Appreciation_Globale[(TauxEvolution>60 & TauxEvolution <=90) & Appreciation_qualite=="Très satisfaisant"]="Moyen++"
          Appreciation_Globale[(TauxEvolution>60 & TauxEvolution <=90) & Appreciation_qualite=="Satisfaisant"]="Moyen+"
          Appreciation_Globale[(TauxEvolution>60 & TauxEvolution <=90) & Appreciation_qualite=="Insatisfaisant"]="Moyen-"

          Appreciation_Globale[TauxEvolution>90 & Appreciation_qualite=="Très satisfaisant"]="Bon++"
          Appreciation_Globale[TauxEvolution>90 & Appreciation_qualite=="Satisfaisant"]="Bon+"
           Appreciation_Globale[TauxEvolution>90 & Appreciation_qualite=="Insatisfaisant"]="Bon-"
         }

           if (trimestre_actuel=="4") {

          Appreciation_Globale=""

          Appreciation_Globale[TauxEvolution<=65 & Appreciation_qualite=="Très satisfaisant"]="Faible++"
          Appreciation_Globale[TauxEvolution<=65 & Appreciation_qualite=="Satisfaisant"]="Faible+"
          Appreciation_Globale[TauxEvolution<=65 & Appreciation_qualite=="Insatisfaisant"]="Faible-"

          Appreciation_Globale[(TauxEvolution>55 & TauxEvolution <=95) & Appreciation_qualite=="Très satisfaisant"]="Moyen++"
          Appreciation_Globale[(TauxEvolution>65 & TauxEvolution <=95) & Appreciation_qualite=="Satisfaisant"]="Moyen+"
          Appreciation_Globale[(TauxEvolution>65 & TauxEvolution <=95) & Appreciation_qualite=="Insatisfaisant"]="Moyen-"

          Appreciation_Globale[TauxEvolution>95 & Appreciation_qualite=="Très satisfaisant"]="Bon++"
          Appreciation_Globale[TauxEvolution>95 & Appreciation_qualite=="Satisfaisant"]="Bon+"
           Appreciation_Globale[TauxEvolution>95 & Appreciation_qualite=="Insatisfaisant"]="Bon-"
         }


        Appreciation_qualite=Appreciation_qualite[,-5]
        TauxEvolution=paste(TauxEvolution,"%")
        Taux_qualite_agent=paste(Taux_qualite_agent,"%")

         Mesure=""

         Mesure[Appreciation_Globale=="Faible++" | Appreciation_Globale=="Faible+" | Appreciation_Globale=="Moyen++" 
                                          |Appreciation_Globale=="Faible+"]="Demande d’explication et décote sur le bonus si motif infondé"

        Mesure[Appreciation_Globale=="Faible-" | Appreciation_Globale=="Moyen-" | Appreciation_Globale=="Bon-"] = "Demande d’explication avec sanction forte et décote sur le bonus si motif infondé"

        Mesure[Appreciation_Globale=="Bon++" | Appreciation_Globale=="Bon+"] = "Impact positif sur le bonus"
