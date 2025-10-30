
cd /tmp
wget https://zlib.net/zlib-1.3.1.tar.gz
tar xf zlib-1.3.1.tar.gz
cd zlib-1.3.1

CC=musl-gcc ./configure --prefix=/usr/local/musl
make
make install

# copy for later use
mkdir -p /usr/local/musl/lib
cp /usr/local/lib/libz.a /usr/local/musl/lib
