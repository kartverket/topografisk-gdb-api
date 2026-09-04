## Publisering av endringer

En naturlig utvidelse av løsningen er løpende publisering av endringer til eksterne abonnenter. Ettersom alle opprettelser, endringer og slettinger behandles av «Forvaltningsserveren», kan denne fungere som en sentral og autoritativ kilde for endringshendelser.

Følgende prinsipper anbefales som utgangspunkt:

- Det bør være mulig å abonnere på opprettelser, endringer og slettinger for bestemte datasett og kartlag.
- Abonnementer bør kunne avgrenses geografisk, for eksempel med en geografisk avgrensningsboks.
- En endringshendelse bør inneholde et begrenset sett med opplysninger, som objektidentifikator (`lokalId`), operasjonstype, tidspunkt, datasett, kartlag og geografisk utstrekning.
- Hele objekter og geometrier bør som hovedregel ikke inngå i hendelsen. Abonnenten kan ved behov hente objektets gjeldende tilstand gjennom API-et. Dette reduserer størrelsen på meldingene og sikrer at abonnenten mottar siste tilgjengelige versjon.
- Endringer som inngår i samme batch- eller transaksjonsoperasjon, bør publiseres samlet eller merkes med en felles identifikator. Abonnentene kan da behandle relaterte endringer som én logisk enhet.
- Leveringsgarantier, rekkefølge, duplikathåndtering, tilgangskontroll og hvor lenge hendelser skal være tilgjengelige, må avklares som en del av produksjonsarkitekturen.

### Teknisk utprøving i PoC-en

Som en del av PoC-en er konseptet implementert og testet med PostgreSQL/PostGIS, en transaksjonell utboks og Redis Streams. Endringer registreres av databasetriggere etter opprettelse, oppdatering og sletting. Registreringen skjer i samme databasetransaksjon som selve objektendringen. Dersom transaksjonen rulles tilbake, blir heller ingen hendelse publisert.

Endringer grupperes per databasetransaksjon, datasett og kartlag. En batchoperasjon som endrer flere objekter i samme kartlag, resulterer derfor i én samlet hendelse med en liste over berørte `lokalId`-verdier og operasjonstyper. For hver hendelse beregner PostGIS en samlet avgrensningsboks som dekker både tidligere og ny geometri. Dette er særlig viktig når objekter flyttes eller slettes. Avgrensningsboksen oppgis i kartlagets native koordinatreferansesystem.

En egen utboksprosess leser ferdigbehandlede hendelser fra databasen og publiserer dem til én Redis Stream per datasett og kartlag. Løsningen gir minst én gangs levering. Hver hendelse har derfor en stabil hendelsesidentifikator som kan brukes av abonnenter til å oppdage og håndtere duplikater.

Kartklienten abonnerer på hendelsene gjennom en Server-Sent Events-endepunkt i den eksisterende webserveren. Det er dermed ikke introdusert en egen abonnementstjeneste i PoC-en. Hver nettleserforbindelse har en selvstendig posisjon i de aktuelle Redis-strømmene, og abonnementet avsluttes når klienten lukker forbindelsen eller forlater siden.

Når kartklienten mottar en hendelse, transformeres hendelsens avgrensningsboks til kartets koordinatsystem og sammenlignes med gjeldende kartutsnitt. Dersom endringen berører et synlig kartlag innenfor kartutsnittet, hentes den aktuelle samlingen på nytt med kartutsnittet som geografisk filter. Denne tilnærmingen håndterer både opprettede, endrede, flyttede og slettede objekter uten at komplette objekter må distribueres i hendelsen.

PoC-en inneholder også en diagnostikkside som viser forbindelsesstatus, antall mottatte hendelser i et rullerende femminuttersvindu, en tidsserie med ti sekunders intervaller og de siste 50 hendelsene med komplett hendelsesinnhold. Dette gjør det mulig å observere hendelsesflyten og kontrollere grupperingen under testing.

Den automatiserte testingen omfatter blant annet:

- generering og etablering av utbokstabell, funksjoner og databasetriggere
- registrering av opprettelser, oppdateringer og slettinger
- gruppering av flere endringer innenfor samme transaksjon
- beregning av samlet avgrensningsboks
- struktur og serialisering av hendelsesinnhold
- gjenopptakelse, retry og publisering fra utboksen
- kontroll av at databaseskjemaet kan anvendes på nytt uten å slette ventende hendelser
- bygging, typekontroll og linting av kartklienten
- etablering og lukking av SSE-forbindelser, inkludert opprydding når klienten kobler fra

Utprøvingen viser at modellen kan gi løpende oppdateringer i kartklienten for opprettelser, endringer, slettinger, oppdateringer av enkeltobjekter, batchoperasjoner og atomiske transaksjoner. Før en produksjonssetting må løsningen likevel tilpasses konkrete krav til blant annet hendelsesteknologi, leveringsgarantier, geografisk filtrering, skalerbarhet, sikkerhet, tilgangsstyring, overvåking og varighet for lagring av hendelser.