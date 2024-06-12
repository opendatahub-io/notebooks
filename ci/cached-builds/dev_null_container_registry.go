package main

import (
	"log"
	"net/http"
)

func main() {
	http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		log.Printf("%s %v", r.Method, r.URL)
	})

	log.Fatal(http.ListenAndServe(":5000", nil))
}
