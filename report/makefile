
targets := $(wildcard tex/*.tex ../img/*)

report.pdf: report.aux report.bbl
	export TEXINPUTS=.:./tex: && pdflatex tex/report.tex

report.aux: $(targets)
	export TEXINPUTS=.:./tex: && pdflatex tex/report.tex

report.bbl: sources.bib report.aux
	bibtex report.aux