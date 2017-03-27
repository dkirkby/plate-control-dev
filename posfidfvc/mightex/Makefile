###
###	Makefile
###
###	mightex_cmd
###

VERSION= 1.00.00

CC=gcc
CFLAGS=-Wall -O2 -DVERSION=\"$(VERSION)\"
DEP=mightex_cmd.o
INCLUDES=-I /usr/lib

.c.o: $(DEP)
	$(CC) $(CFLAGS) $(INCLUDES) -c $<

mightex_cmd: $(DEP)
	$(CC) $(CFLAGS) $(DEP) -ludev -o $@

clean:
	rm -f *.o *~ core mightex_cmd
