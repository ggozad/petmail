
.PHONY: n1 n2 relay stop bounce-all bounce rebuild
n1:
	-./bin/petmail stop n1
	rm -rf n1
	./bin/petmail create-node n1
n2:
	-./bin/petmail stop n2
	rm -rf n2
	./bin/petmail create-node n2
#relay:
#	-./bin/petmail stop relay
#	rm -rf relay
#	./bin/petmail create-relay relay

stop:
	-./bin/petmail stop n1
	-./bin/petmail stop n2
#	-./bin/petmail stop relay
bounce-all:
#	-./bin/petmail restart relay
#	sleep 1
	-./bin/petmail restart n1
	-./bin/petmail restart n2
bounce:
	-./bin/petmail restart n1
	-./bin/petmail restart n2

rebuild: stop n1 n2 bounce

dump-n1:
	sqlite3 n1/petmail.db .dump
dump-n2:
	sqlite3 n2/petmail.db .dump
