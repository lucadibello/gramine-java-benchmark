package com.benchmark.teaclave.common;

import java.io.Serializable;

public final class Ack implements Serializable {
    private static final long serialVersionUID = 1L;

    private final int ID;
    private final int value;

    public Ack(int id, int value) {
        this.ID = id;
        this.value = value;
    }

    public int getValue() {
        return this.value;
    }

    public int getId() {
        return this.ID;
    }

    @Override
    public String toString() {
        return "Ack{ID=" + ID + ", value=" + value + "}";
    }
}
