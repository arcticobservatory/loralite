#!/bin/bash

while IFS="" read -r p || [ -n "$p" ]; do
    while true
    do
        num=`ps aux|grep "python3 simulator*"|grep $USER|grep -v grep|wc -l`
        
        if [ $num -lt 8 ]
        then
            break
        else
            echo "[$num] Sleeping for 1s"
            sleep 10
        fi
    done
    current=`ps aux|grep "python3 simulator*"|grep $USER|grep -v grep|wc -l`
    echo "[$current] Executing ${p}"
    ${p} > /dev/null 2>&1 &
done < $1

echo "Finished spawning simulations. Waiting for the last one to finish..."
while true
do
    num=`ps aux|grep "python3 simulator*"|grep $USER|grep -v grep|wc -l`
    if [ $num -gt 0 ]
    then
        echo "Still running: $num"
        sleep 10
    else
        break
    fi
done