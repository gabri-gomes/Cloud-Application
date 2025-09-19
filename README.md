# Começar aplicação : 

minikube start

minikube addons enable metrics-server

eval $(minikube docker-env)

docker build -t mycloud_backend  ./backend
docker build -t mycloud_executor ./executor
docker build -t mycloud_worker   ./backend   

kubectl apply -f k8s/

# esperar estejam todos connectados, pode demorar 30 segundos
kubectl get pods -o wide 

# Aceder ao app via NodePort 
minikube service backend --url

# Colar na web e rodar 
exemplo : "http://127.0.0.3:42929"




# Para parar e eliminar : 

minikube stop 

minikube delete

