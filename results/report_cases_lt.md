# Keturi ataskaitos atvejai

Pastaba: pagrindiniame eksperimente Qwen išsaugojo tik struktūrinę klasės žymą, todėl klaidų analizė yra išorinė loginė analizė, paremta prielaidomis, Prover9 įrodymais ir Mace4 kontrmodeliais; ji nėra pateikiama kaip modelio paslėpta samprotavimo eiga.

## Teisingai nustatyta, kad išvada seka

**Atvejis:** `folio50-001` / `concl_20_13`  
**Etalonas:** `True`  
**Qwen3-8B:** `True`  
**Prover9/Mace4:** `True`

### Prielaidos

1. A Japanese game company created the game the Legend of Zelda.
2. All games on the Top 10 list are made by Japanese game companies.
3. If a game sells more than one million copies, then it will be included in the Top 10 list.
4. The Legend of Zelda sold more than one million copies.

### Išvada

The Legend of Zelda is on the Top 10 list.

### FOL išvada

```text
InTop10(theLegendofZelda)
```

### Analizė

Iš prielaidų gauname, kad „The Legend of Zelda“ yra žaidimas ir kad jo parduota daugiau nei vienas milijonas kopijų. Universalioji taisyklė teigia, kad kiekvienas žaidimas, kurio parduota daugiau nei vienas milijonas kopijų, patenka į Top 10 sąrašą. Pritaikius modus ponens tiesiogiai gaunama išvada `InTop10(theLegendofZelda)`. Qwen ir Prover9 sutapo su etalonine žyma `True`.

### Automatinio tikrinimo failai

`prover9_outputs/folio50-001_conclusion_prover9.txt`, `prover9_outputs/folio50-001_negated_conclusion_prover9.txt`, `prover9_outputs/folio50-001_negated_conclusion_mace4.txt`


## Teisingai nustatyta, kad išvados neiginys seka

**Atvejis:** `folio50-002` / `concl_20_15`  
**Etalonas:** `False`  
**Qwen3-8B:** `False`  
**Prover9/Mace4:** `False`

### Prielaidos

1. A Japanese game company created the game the Legend of Zelda.
2. All games on the Top 10 list are made by Japanese game companies.
3. If a game sells more than one million copies, then it will be included in the Top 10 list.
4. The Legend of Zelda sold more than one million copies.

### Išvada

The Legend of Zelda is not on the Top 10 list.

### FOL išvada

```text
¬InTop10(theLegendofZelda)
```

### Analizė

Ketvirtoji prielaida teigia, kad „The Legend of Zelda“ parduota daugiau nei milijonas kopijų, o trečioji taisyklė kiekvieną tokį žaidimą įtraukia į Top 10 sąrašą. Todėl `InTop10(theLegendofZelda)` seka tiesiogiai, o pateikta išvada yra būtent šio teiginio neiginys. Prover9 įrodė išvados neiginį, o Qwen teisingai pasirinko klasę `False`.

### Automatinio tikrinimo failai

`prover9_outputs/folio50-002_conclusion_prover9.txt`, `prover9_outputs/folio50-002_conclusion_mace4.txt`, `prover9_outputs/folio50-002_negated_conclusion_prover9.txt`


## Klaida: išvada turėjo sekti, bet Qwen pasirinko „False“

**Atvejis:** `folio50-018` / `concl_306_84`  
**Etalonas:** `True`  
**Qwen3-8B:** `False`  
**Prover9/Mace4:** `True`

### Prielaidos

1. If a restaurant is listed in Yelp's recommendations, then the restaurant has not received many negative reviews.
2. All restaurants with a rating greater than four are listed in Yelp's recommendations.
3. Some restaurants that do not provide take-out service receive many negative reviews.
4. All restaurants that are popular among local residents have ratings greater than four.
5. The Hamden Plaza Subway store has a rating greater than four, or it is popular among local residents.

### Išvada

If the Hamden Plaza Subway store provides take-out service and receives many negative reviews, then its rating is greater than 4 and it does not provide take-out service.

### FOL išvada

```text
(Provide(hamdenPlazaSubway, takeOutService) ∧ ReceiveManyNegativeReviews(hamdenPlazaSubway)) → (∃y (HaveRating(hamdenPlazaSubway, y) ∧ GreaterThan(y, four)) ∧ ¬Provide(hamdenPlazaSubway, takeOutService))
```

### Analizė

Penktoji prielaida užtikrina, kad Hamden Plaza Subway reitingas yra didesnis nei keturi: tai teigiama tiesiogiai arba gaunama iš populiarumo pagal ketvirtąją taisyklę. Pagal antrąją ir pirmąją taisykles restoranas įtrauktas į Yelp rekomendacijas ir negauna daug neigiamų atsiliepimų. Todėl išvados antecedentas, kuriame kartu teigiama, kad restoranas teikia išsinešimo paslaugą ir gauna daug neigiamų atsiliepimų, negali būti teisingas. Materialioji implikacija su klaidingu antecedentu yra teisinga. Prover9 tai įrodė; Qwen klaida rodo neatsižvelgimą į vakuozų implikacijos teisingumą.

### Automatinio tikrinimo failai

`prover9_outputs/folio50-018_conclusion_prover9.txt`, `prover9_outputs/folio50-018_negated_conclusion_prover9.txt`, `prover9_outputs/folio50-018_negated_conclusion_mace4.txt`


## Klaida: išvada neturėjo sekti, bet Qwen pasirinko „True“

**Atvejis:** `folio50-005` / `concl_452_30`  
**Etalonas:** `False`  
**Qwen3-8B:** `True`  
**Prover9/Mace4:** `False`

### Prielaidos

1. All aliens are extraterrestrials.
2. If someone is from Mars, then they are an alien.
3. No extraterrestrials are human.
4. All highly intelligent beings from Earth are humans.
5. Marvin is a highly intelligent being.
6. Marvin is either from Earth and from Mars, or he is from neither.
7. If Marvin is not from Earth, then Marvin is an extraterrestrial.

### Išvada

If Marvin is not from Mars, then Marvin is a human.

### FOL išvada

```text
¬From(marvin, mars) → Human(marvin)
```

### Analizė

Šeštoji prielaida `¬(From(earth) ⊕ From(mars))` reiškia, kad abu teiginiai turi vienodą reikšmę. Atvejis, kai abu teisingi, sukelia prieštaravimą: Marsas veda į `Alien`, `Extraterrestrial` ir `¬Human`, o Žemė kartu su Marvino aukštu intelektu veda į `Human`. Taigi lieka atvejis, kai abu klaidingi. Iš `¬From(earth)` gaunama `Extraterrestrial` ir `¬Human`, todėl sąlyginio teiginio antecedentas `¬From(mars)` teisingas, o konsekventas `Human` klaidingas. Prover9 įrodė išvados neiginį. Qwen klaida susijusi su neigiamo XOR kaip lygiavertiškumo ir materialiosios implikacijos neįvertinimu.

### Automatinio tikrinimo failai

`prover9_outputs/folio50-005_conclusion_prover9.txt`, `prover9_outputs/folio50-005_conclusion_mace4.txt`, `prover9_outputs/folio50-005_negated_conclusion_prover9.txt`
