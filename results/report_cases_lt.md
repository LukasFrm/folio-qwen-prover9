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


## Teisingai nustatyta, kad išvada neseka

**Atvejis:** `folio50-002` / `concl_20_14`  
**Etalonas:** `Uncertain`  
**Qwen3-8B:** `Uncertain`  
**Prover9/Mace4:** `Uncertain`

### Prielaidos

1. A Japanese game company created the game the Legend of Zelda.
2. All games on the Top 10 list are made by Japanese game companies.
3. If a game sells more than one million copies, then it will be included in the Top 10 list.
4. The Legend of Zelda sold more than one million copies.

### Išvada

FIFA 22 is made by a Japanese video game company.

### FOL išvada

```text
∃x(Created(x, fifa22) ∧ Japanese(x) ∧ VideoGameCompany(x))
```

### Analizė

Visos prielaidos aprašo „The Legend of Zelda“; nė viena prielaida nemini FIFA 22 ir nenustato jo kūrėjo. Todėl negalima įrodyti nei egzistencinės išvados apie japonų bendrovę, sukūrusią FIFA 22, nei jos neiginio. Mace4 rado po baigtinį kontrmodelį abiem kryptims, todėl `Uncertain` yra pagrįsta žyma. Qwen šį neapibrėžtumą atpažino teisingai.

### Automatinio tikrinimo failai

`prover9_outputs/folio50-002_conclusion_prover9.txt`, `prover9_outputs/folio50-002_conclusion_mace4.txt`, `prover9_outputs/folio50-002_negated_conclusion_prover9.txt`, `prover9_outputs/folio50-002_negated_conclusion_mace4.txt`


## Klaida: išvada turėjo sekti, bet Qwen pasirinko „Uncertain“

**Atvejis:** `folio50-024` / `concl_379_104`  
**Etalonas:** `True`  
**Qwen3-8B:** `Uncertain`  
**Prover9/Mace4:** `True`

### Prielaidos

1. People who are born in a multiple birth with siblings spend a lot of time hanging out with and playing with their siblings.
2. If people have siblings who were born together, then they were born in a multiple birth.
3. If people complain often about annoying siblings, then they have siblings who were born together.
4. If people live at home, then they do not live with strangers.
5. If people spend a lot of time hanging out with and playing with their siblings, then they often live at home.
6. Luke either is a baby born in a multiple birth and lives with strangers, or is not a baby born in a multiple birth and does not live with strangers.

### Išvada

Luke is neither born in a multiple birth nor complains often about annoying siblings.

### FOL išvada

```text
¬BornIn(luke, multipleBirth) ∧ ¬ComplainAboutOften(luke, annoyingSiblings)
```

### Analizė

Šeštoji formalizuota prielaida yra XOR neiginys: Luke gimimas daugiavaisiame gimdyme ir gyvenimas su nepažįstamaisiais turi vienodą teisingumo reikšmę. Tarkime, kad `BornIn(luke, multipleBirth)` teisinga. Tuomet pagal 1 ir 5 prielaidas Luke leidžia laiką su broliais ar seserimis ir gyvena namuose; pagal 4 prielaidą jis negyvena su nepažįstamaisiais. Tačiau XOR neiginys iš teisingo `BornIn` reikalauja teisingo `LiveWith`, todėl gaunamas prieštaravimas. Vadinasi, `BornIn` yra klaidinga. Jei Luke dažnai skųstųsi broliais ar seserimis, 3 ir 2 prielaidos vėl leistų išvesti `BornIn`; todėl klaidingas ir `ComplainAboutOften`. Prover9 įrodė visą konjunkcinę išvadą. Qwen klaidos vieta – nepakankamai išnaudotas XOR neiginys ir netiesioginis įrodymas prieštaravimu.

### Automatinio tikrinimo failai

`prover9_outputs/folio50-024_conclusion_prover9.txt`, `prover9_outputs/folio50-024_negated_conclusion_prover9.txt`, `prover9_outputs/folio50-024_negated_conclusion_mace4.txt`


## Klaida: išvada neturėjo sekti, bet Qwen pasirinko „True“

**Atvejis:** `folio50-007` / `concl_159_47`  
**Etalonas:** `Uncertain`  
**Qwen3-8B:** `True`  
**Prover9/Mace4:** `Uncertain`

### Prielaidos

1. There are four seasons in a year: Spring, Summer, Fall, and Winter.
2. All students who want to have a long vacation have summer as their favorite season.
3. Emma's favorite season is summer.
4. Mia's favorite season is not the same as Emma's.
5. James wants to have a long vacation.

### Išvada

James's favorite season is summer.

### FOL išvada

```text
Favorite(james, summer)
```

### Analizė

Taisyklės antecedentas yra konjunkcija: vasara yra mėgstamiausias sezonas tik tiems asmenims, kurie ir yra studentai, ir nori ilgų atostogų. Apie Jamesą žinoma tik antroji sąlyga – `Want(james, longVacation)`; prielaidos `Student(james)` nėra. Todėl modus ponens taikyti negalima. Mace4 rado modelį, kuriame Jameso mėgstamiausias sezonas yra vasara, ir modelį, kuriame taip nėra. Qwen klaida atitinka antecedento dalies praleidimą: noras turėti ilgas atostogas buvo traktuotas kaip pakankama, nors taisyklėje jis yra tik viena iš dviejų būtinų sąlygų.

### Automatinio tikrinimo failai

`prover9_outputs/folio50-007_conclusion_prover9.txt`, `prover9_outputs/folio50-007_conclusion_mace4.txt`, `prover9_outputs/folio50-007_negated_conclusion_prover9.txt`, `prover9_outputs/folio50-007_negated_conclusion_mace4.txt`
