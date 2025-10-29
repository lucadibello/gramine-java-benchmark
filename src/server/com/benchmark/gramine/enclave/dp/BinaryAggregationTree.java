package com.benchmark.gramine.enclave.dp;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

public class BinaryAggregationTree implements Serializable {
    private Double curPrivateSum = 0.00;
    private final ArrayList<Double> tree;
    private final int height;

    public BinaryAggregationTree(int n, double sigma) {
        this.height = (int) Math.ceil(Math.log(n) / Math.log(2));
        tree = initializeTree(n, sigma);
    }

    public Double getTotalSum() {
        return curPrivateSum;
    }

    private ArrayList<Double> initializeTree(int n, double sigma) {
        int numLeaves = (int) Math.pow(2, height);
        ArrayList<Double> tree = new ArrayList<>();
        int treeSize = 2 * numLeaves - 1;
        Random rand = new Random();
        for (int j = 0; j < treeSize; j++) {
            Double noise = rand.nextGaussian() * sigma;
            tree.add(noise);
        }
        return tree;
    }

    public Double addToTree(int i, Double value) {
        int numLeaves = (tree.size() + 1) / 2;
        {
            int nodeIndex = numLeaves - 1 + i;

            while (nodeIndex > 0) {
                Double curVal = tree.get(nodeIndex);
                tree.set(nodeIndex, curVal + value);
                nodeIndex = (nodeIndex - 1) / 2;
            }
            tree.set(nodeIndex, tree.get(nodeIndex) + value);
        }

        double sPriv = 0.00;
        String indexBinaryRepr = Integer.toBinaryString(i + 1);
        indexBinaryRepr = String.format("%" + (height + 1) + "s", indexBinaryRepr).replace(' ', '0');
        String pathBinary = Integer.toBinaryString(i);
        pathBinary = String.format("%" + height + "s", pathBinary).replace(' ', '0');

        int nodeIndex = 0;
        for (int j = 0; j < height + 1; j++) {
            char vertexBit = indexBinaryRepr.charAt(j);

            if (vertexBit == '1') {
                int leftSibling = (nodeIndex % 2 == 0) ? nodeIndex - 1 : nodeIndex;

                if (nodeIndex == 0) {
                    leftSibling = nodeIndex;
                }

                sPriv = sPriv + tree.get(leftSibling);
            }
            if (j < height) {
                char pathBit = pathBinary.charAt(j);
                int leftChild = 2 * nodeIndex + 1;
                int rightChild = 2 * nodeIndex + 2;

                nodeIndex = (pathBit == '0') ? leftChild : rightChild;
            }

        }
        curPrivateSum = sPriv;
        return sPriv;
    }

    public static Double hierarchicalPerturbationEnc(ArrayList<Double> data, BinaryAggregationTree bat) {
        for (int i = 0; i < data.size(); i++) {
            bat.addToTree(i, data.get(i));
        }
        return bat.getTotalSum();
    }

    public List<Double> getTree() {
        return new ArrayList<>(tree);
    }
}
